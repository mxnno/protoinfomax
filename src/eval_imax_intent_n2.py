import numpy
import os
import sys
sys.path.append(os.getcwd())
import numpy as np
import torch

import configparser
from all_parameters_intent import get_all_parameters
import torch.nn.functional as F
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
from workspace_intent import SENT_WORDID, SENT_LABELID, SENT_WORD_MASK, SENT_ORIGINAL_TXT
from torch.utils.data import Dataset, DataLoader, RandomSampler, SubsetRandomSampler
import argparse
from utils_torch_intent import compute_values, get_data, compute_values_eval
from experiment_imax_intent import RunExperiment
from workspace_intent import workspace
from model_imax_intent import *
from vocabulary_intent import get_word_info
import math
import random


from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer

import nltk
nltk.data.path.append("/content/nltk_data/")
import re
import string

from gensim.models.word2vec import Word2Vec, LineSentence
from gensim.scripts.glove2word2vec import glove2word2vec
from gensim.models.keyedvectors import KeyedVectors

import fasttext
import fasttext.util
from gensim.models.fasttext import load_facebook_model
from gensim.models.fasttext import FastText as FT_gensim
from gensim.test.utils import datapath
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
from random import shuffle

from wikipedia2vec import Wikipedia2Vec

from pprint import pprint
from copy import deepcopy

import time
from datetime import datetime, timedelta
from gensim import utils, matutils

# NLTK Stop words
from gensim.utils import simple_preprocess
from nltk.corpus import stopwords
stop_words = stopwords.words('english')

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

import _pickle as cPickle

def read_pickle(filepath, filename):

        f = open(os.path.join(filepath, filename), 'rb')
        read_file = cPickle.load(f)
        f.close()

        return read_file

def save_pickle(filepath, filename, data):

    f = open(os.path.join(filepath, filename), 'wb')
    cPickle.dump(data, f)
    print(" file saved to: %s"%(os.path.join(filepath, filename)))
    f.close()



def load_w2v():

    vocab_new = []
    word_vecs_new = []
    zeros_init = [float(0.)] * 100

    model = Word2Vec.load('/content/protoinfomax/embeddings/w2v_fasttext_intent.model')
    vocab = list(model.wv.vocab)
    word_vecs = model.wv.vectors
    w2v = model.wv

    word_vecs = word_vecs.tolist()
    
    vocab_new.append('</s>') #0
    word_vecs_new.append(zeros_init)
    vocab_new.append('<unk>') #1
    word_vecs_new.append(zeros_init)

    vocab_new.extend(vocab)
    word_vecs_new.extend(word_vecs)

    word_vecs_new = np.array(word_vecs_new)

    return vocab_new, word_vecs_new

class TestLoader(Dataset):
    def __init__(self, data, params):

        self.data = data
        
        self.params = params
        self.batch_size = self.params['batch_size']
        self.X_sup = None
        self.X_sup_mask = None
        self.Y_sup = None
        self.X_q = None
        self.X_q_mask = None
        self.Y_q = None
        self.Y_sup_onehot  = None
        self.Y_q_onehot = None

        self.pair_data = self._build_pairs()

    def get_one_hot(self, y_target, classe_list):

        cls_id_map = dict()
        for lid in classe_list:
                    cls_id_map[lid] = len(cls_id_map)


        y_target_one_hot = numpy.zeros([len(y_target), len(cls_id_map)])
        for k in range(len(y_target)):
            y_target_one_hot[k][cls_id_map[y_target[k]]] = 1.0

        return y_target_one_hot

    def get_supporting_set(self, test_workspace):

        all_ss_info = test_workspace.get_flatten_supporting_set()[:self.params['min_ss_size']]

        strbatch = [s[SENT_ORIGINAL_TXT] for s in
                    all_ss_info]
        txtbatch = [s[SENT_WORDID] for s in
                    all_ss_info]
        maskbatch = [s[SENT_WORD_MASK] for s in
                     all_ss_info]
        ybatch = [s[SENT_LABELID] for s in
                  all_ss_info]

        #print('test_workspace.labels_in_train', len(test_workspace.labels_in_train))
        nClasses = 2
        ybatch_one_shot = self.get_one_hot(ybatch, range(nClasses))

        
        return strbatch, txtbatch, maskbatch, ybatch, ybatch_one_shot

    def _build_pairs(self):


        all_examples = []
       
        domain_examples = []
       
        for b in range(len(self.data)):
            # for sampling query (get n-query per intent/class)
            qcurr_dev_workspace = self.data[b]
            nClasses = 2

            for target_set, target_set_file in zip(qcurr_dev_workspace.target_sets, qcurr_dev_workspace.target_sets_files):                  
                #print('Testing: ', target_set_file)
                if str(target_set_file).find('test') != -1:
                                        
                    input_target_sent_test= [target_sentence[SENT_WORDID] for target_sentence in target_set]
                    in_txt= [target_sentence[SENT_ORIGINAL_TXT] for target_sentence in target_set]
                    target_sent_mask_test= [target_sentence[SENT_WORD_MASK] for target_sentence in target_set]
                    groundtruth_id = [target_sentence[SENT_LABELID] for target_sentence in target_set]
                    groundtruth = [qcurr_dev_workspace.lblist[gt_id] for gt_id in groundtruth_id]

                    input_target_sent_test = np.array(input_target_sent_test)
                    in_txt = np.array(in_txt)
                    target_sent_mask_test = np.array(target_sent_mask_test)
                    groundtruth_id = np.array(groundtruth_id)
                    groundtruth = np.array(groundtruth)

                  

                    for idx in range(len(input_target_sent_test)):

                        X_q = numpy.array(input_target_sent_test[idx], dtype='int')
                        X_q_mask = numpy.array(target_sent_mask_test[idx], dtype='int')
                        Y_q = numpy.array(groundtruth_id[idx], dtype='int')

                        len_ = np.count_nonzero(X_q)
                        self.len_X_q = [len_]
                        self.len_X_q = np.array(self.len_X_q)

                        #print("self.len_X_q shape:", self.len_X_q.shape)
                    
                        self.X_q = numpy.array([X_q])
                        self.X_q_mask = numpy.array([X_q_mask])
                        self.Y_q = numpy.array([Y_q])

                        # sampling support examples
                        self.X_sup = []
                        self.X_sup_mask = []
                        self.Y_sup_onehot = []
                        self.Y_sup =[]
                        self.len_X_sup = []

                        # for sampling support
                        
                        nClasses = 2
                        sup_str, support_txtid, support_mask, support_ybatch, support_ybatch_one_shot = self.get_supporting_set(qcurr_dev_workspace)

                        support_txtid= np.array(support_txtid)
                        support_ybatch_one_shot= np.array(support_ybatch_one_shot)
                        support_ybatch= np.array(support_ybatch)
                        support_mask= np.array(support_mask)
               
                        support_txtid = support_txtid.reshape((1,self.params['min_ss_size'],-1))
                        support_ybatch_one_shot = support_ybatch_one_shot.reshape((1,self.params['min_ss_size'],-1))
                        support_ybatch = support_ybatch.reshape((1,self.params['min_ss_size']))
                        support_mask = support_mask.reshape((1,self.params['min_ss_size'], -1))
                      

                        len_X_sup = []
                        for sup in support_txtid:
                            lens = []
                            for d in sup:
                                lens.append(np.count_nonzero(d))
                            len_X_sup.append(lens)

                        self.X_sup = numpy.array(support_txtid.tolist())
                        self.X_sup_mask = numpy.array(support_mask.tolist())
                        self.Y_sup_onehot = numpy.array(support_ybatch_one_shot.tolist())
                        self.Y_sup = numpy.array(support_ybatch.tolist())
                        self.len_X_sup = numpy.array(len_X_sup)
                   
                        example_dict = {'X_sup': torch.from_numpy(self.X_sup.astype(np.int64)), 'X_sup_len': torch.from_numpy(self.len_X_sup), 'Y_sup': torch.from_numpy(self.Y_sup), 'Y_sup_oh': torch.from_numpy(self.Y_sup_onehot.astype(np.int64)), 'X_q':torch.from_numpy(self.X_q.astype(np.int64)), 'X_q_len': torch.from_numpy(self.len_X_q), 'Y_q': torch.from_numpy(self.Y_q), 'target_set_file': target_set_file}

                        domain_examples.append(example_dict)

            all_examples.append(domain_examples)

        return all_examples

    def __len__(self):
        return len(self.pair_data)

    def __getitem__(self, index):
        return self.pair_data[index]

class AmazonLoader(Dataset):
    def __init__(self, data, params):

        self.data = data
        
        self.params = params
        self.batch_size = self.params['batch_size']
        self.X_sup = None
        self.X_sup_mask = None
        self.Y_sup = None
        self.X_q = None
        self.X_q_mask = None
        self.Y_q = None
        self.X_neg = None
        self.X_neg_mask = None
        self.selected_labels = None
        self.Y_sup_onehot  = None
        self.Y_q_onehot = None

        self.pair_data = self._build_pairs()

    def get_train_batch(self, train_workspace, all_ood_workspaces):

        sent_list = train_workspace.target_sets[0]
        nClasses_in_Train = len(train_workspace.labels_in_train)

        sampled_class_size = int(self.params['sampling_classes'])
        sampled_classes = train_workspace.sample_classes(sampled_class_size)

        sentence_size_per_intent = max(1, int(self.params['min_ss_size']))
        cls_ = np.arange(10)

        sent_id_batch = []
        for b in range(100):
            selected_label = random.choice(sampled_classes)

            #print("selected_label:", selected_label)
            #sys.stdout.flush()

            selected_utt = random.choice(train_workspace.train_intent2ids_list[selected_label])
            #print("selected_utt:", selected_utt)
            sent_id_batch.append(int(selected_utt))

        #print("sent_id_batch len:", len(sent_id_batch)) # (bs,)

        x_target_wid = [sent_list[i][SENT_WORDID] for i in sent_id_batch]
        y_target = [sent_list[i][SENT_LABELID] for i in sent_id_batch]
        x_target_mask = [sent_list[i][SENT_WORD_MASK] for i in sent_id_batch]

        x_support_set_wid = []
        y_support_set = []
        x_support_set_mask = []
        x_ood_wid = []
        x_ood_mask = []
        y_ood = []

        for target_sid in range(len(sent_id_batch)):
            selected_ood_sent_infos = []
            for _ in range(self.params['ood_example_size']):
                selected_ood_workspace = numpy.random.choice(all_ood_workspaces)
                fss = selected_ood_workspace.get_flatten_supporting_set()
                selected_id = numpy.random.choice([i for i in range(len(fss))])
                selected_ood_sent_info = fss[selected_id]
                selected_ood_sent_infos.append(selected_ood_sent_info)

            ss_sent_info = train_workspace.select_support_set(sentence_size_per_intent,
                                                              0,
                                                              sent_id_batch[target_sid], sampled_classes)


            x_support_set_wid_per_sent = [sinfo[SENT_WORDID] for sinfo in ss_sent_info]
            y_support_set_per_sent = [sinfo[SENT_LABELID] for sinfo in ss_sent_info]
            x_support_set_mask_per_sent = [sinfo[SENT_WORD_MASK] for sinfo in ss_sent_info]

            x_support_set_wid_per_sent= np.array(x_support_set_wid_per_sent)
            y_support_set_per_sent= np.array(y_support_set_per_sent)
            x_support_set_mask_per_sent= np.array(x_support_set_mask_per_sent)
            
            x_support_set_wid_per_sent = x_support_set_wid_per_sent.reshape((10,self.params['min_ss_size'],-1))
            y_support_set_per_sent = y_support_set_per_sent.reshape((10,self.params['min_ss_size']))
            x_support_set_mask_per_sent = x_support_set_mask_per_sent.reshape((10,self.params['min_ss_size'], -1))
            
            x_support_set_mask.extend(x_support_set_mask_per_sent.tolist())
            x_support_set_wid.extend(x_support_set_wid_per_sent.tolist())
            y_support_set.extend(y_support_set_per_sent.tolist())

            x_ood_wid_per_sent = [sinfo[SENT_WORDID] for sinfo in selected_ood_sent_infos]
            x_ood_mask_per_sent = [sinfo[SENT_WORD_MASK] for sinfo in selected_ood_sent_infos]
            x_ood_label_per_sent = [sinfo[SENT_LABELID] for sinfo in selected_ood_sent_infos]
            x_ood_wid.append(x_ood_wid_per_sent)
            x_ood_mask.append(x_ood_mask_per_sent)
            y_ood.append(x_ood_label_per_sent)

        y_ood = np.array(y_ood)
        y_ood = y_ood.reshape((len(sent_id_batch))).tolist()
        
        return x_support_set_wid, \
            y_support_set,  \
            x_support_set_mask,  \
            x_target_wid, \
            y_target,  \
            x_target_mask, \
            x_ood_wid,  \
            x_ood_mask, \
            y_ood


    def get_support_set_one_hot(self, support_set, classe_list):
        cls_id_map = dict()
        for lid in classe_list:
                    cls_id_map[lid] = len(cls_id_map)

        support_set_one_hot = numpy.zeros([len(support_set), 
                                          len(support_set[0]),
                                          len(cls_id_map)])
        for k in range(len(support_set)):
            for j in range(len(support_set[k])):
                support_set_one_hot[k][j][cls_id_map[support_set[k][j]]] = 1.0

        return support_set_one_hot

    def get_one_hot(self, y_target, classe_list):
        cls_id_map = dict()
        for lid in classe_list:
                    cls_id_map[lid] = len(cls_id_map)

        y_target_one_hot = numpy.zeros([len(y_target), len(cls_id_map)])
        for k in range(len(y_target)):
            y_target_one_hot[k][cls_id_map[y_target[k]]] = 1.0
        return y_target_one_hot


    def _build_pairs(self):

        examples = []
        
        bs = np.random.permutation(range(len(self.data))).tolist()

        for b in bs:

            self.X_sup = []
            self.Y_sup = [] 
            self.X_sup_mask = []
            self.X_q = [] 
            self.Y_q = [] 
            self.X_q_mask = []
            self.X_neg = [] 
            self.X_neg_mask = []
            self.Y_neg = []
            self.Y_sup_onehot = []
            self.Y_q_onehot = []
            self.Y_neg_onehot = []
            self.X_sup_len = []
            self.Xq_len = []
            self.X_neg_len = []
                 
            curr_workspace = self.data[b]
            ood_wordspace = self.data[:b] + self.data[b+1:]

            target_sets_files = curr_workspace.target_sets_files

            X_sup, Y_sup, X_sup_mask, \
            X_q, Y_q, X_q_mask, \
            X_neg, X_neg_mask, Y_neg = \
            self.get_train_batch(curr_workspace, ood_wordspace)
           
            Y_sup_onehot = self.get_support_set_one_hot(Y_sup, range(10))
            Y_q_onehot = self.get_one_hot(Y_q, range(10))
            Y_neg_onehot = self.get_one_hot(Y_neg, range(10))
            
            X_sup_len_ = []
            for sup in X_sup:
                lens = []
                for d in sup:
                    lens.append(np.count_nonzero(d))
                X_sup_len_.append(lens)

            Xq_len_ = []
            for sup in X_q:
                len_ = np.count_nonzero(sup)
                Xq_len_.append([len_])

            X_neg_len_ = []
            for sup in X_neg:
                len_ = np.count_nonzero(sup)
                X_neg_len_.append([len_])

            self.X_sup = X_sup
            self.Y_sup = Y_sup
            self.X_sup_mask = X_sup_mask
            self.X_q = X_q
            self.Y_q = Y_q
            self.X_q_mask = X_q_mask
            self.X_neg = X_neg
            self.X_neg_mask = X_neg_mask
            self.Y_sup_onehot = Y_sup_onehot
            self.Y_q_onehot=Y_q_onehot
            self.Y_neg=Y_neg
            self.Y_neg_onehot=Y_neg_onehot
            self.X_sup_len=X_sup_len_
            self.Xq_len=Xq_len_
            self.X_neg_len=X_neg_len_

            self.X_sup = np.array(self.X_sup)
            self.Y_sup = np.array(self.Y_sup)
            self.X_sup_mask = np.array(self.X_sup_mask)
            self.X_q = np.array(self.X_q)
            self.Y_q = np.array(self.Y_q)
            self.X_q_mask = np.array(self.X_q_mask)
            self.X_neg = np.array(self.X_neg)
            self.X_neg_mask = np.array(self.X_neg_mask)
            self.Y_sup_onehot = np.array(self.Y_sup_onehot)
            self.Y_q_onehot = np.array(self.Y_q_onehot)
            self.Y_neg = np.array(self.Y_neg)
            self.Y_neg_onehot = np.array(self.Y_neg_onehot)
            self.X_sup_len = np.array(self.X_sup_len)
            self.Xq_len = np.array(self.Xq_len)
            self.X_neg_len = np.array(self.X_neg_len)
      

            example_dict = {'X_sup': torch.from_numpy(self.X_sup.astype(np.int64)), 'X_sup_len': torch.from_numpy(self.X_sup_len), 'Y_sup': torch.from_numpy(self.Y_sup), 'Y_sup_oh': torch.from_numpy(self.Y_sup_onehot.astype(np.int64)), 'X_q':torch.from_numpy(self.X_q.astype(np.int64)), 'Xq_len':torch.from_numpy(self.Xq_len), 'Y_q': torch.from_numpy(self.Y_q), 'Y_q_oh': torch.from_numpy(self.Y_q_onehot.astype(np.int64)), 'X_neg': torch.from_numpy(self.X_neg.astype(np.int64)), 'X_neg_len': torch.from_numpy(self.X_neg_len), 'Y_neg': torch.from_numpy(self.Y_neg), 'Y_neg_oh': torch.from_numpy(self.Y_neg_onehot.astype(np.int64)), 'target_sets_files': target_sets_files}

            examples.append(example_dict)


        return examples
        
    def __len__(self):
        return len(self.pair_data)

    def __getitem__(self, index):
        return self.pair_data[index]


def eval_model(params, model, experiment, optimizer, epoch):

    TEST_FILE_INDEX = 2
    DATA_PATH = '/content/protoinfomax/data'
    RSL_PATH = '/content/protoinfomax/results'

    _, dev_data, test_data = read_pickle(DATA_PATH, 'tr_dev_te_intent.pkl')

    dev_set = TestLoader(dev_data, params)
    test_set = TestLoader(test_data, params)

   
    print("len dev_set:", len(dev_set))
    sys.stdout.flush()
    print("len test_set:", len(test_set))
    sys.stdout.flush()

    v_eer_ = 0.0
    v_acc_ideal_ = 0.0
    v_acc_ = 0.0

    t_eer_ = 0.0
    t_acc_ideal_ = 0.0
    t_acc_ = 0.0

    v_avg_conf_ood_ = 0.0
    t_avg_conf_ood_ = 0.0

    v_probs_ = []
    v_gts_ = []

    t_probs_ = []
    t_gts_ = []

    for c in range(len(test_set)):


        id_val = np.array([c])
        valid_sampler = SubsetRandomSampler(id_val)
        test_sampler = SubsetRandomSampler(id_val)

        valid_dl = DataLoader(dev_set, sampler=valid_sampler, batch_size=1)
        test_dl = DataLoader(test_set, sampler=test_sampler, batch_size=1)
        
        v_macro_avg_eer, v_macro_avg_far, v_macro_avg_frr, \
        v_macro_avg_acc_ideal, v_macro_avg_acc, \
        val_output_info_list, domain_val, v_avg_conf_ood, v_probs, v_gts = compute_values_eval(params, experiment, valid_dl, "validation_dat")

        print("eer, onacc_ideal, onacc: %.3f, %.3f, %.3f" %
          (v_macro_avg_eer, 
           v_macro_avg_acc_ideal, 
           v_macro_avg_acc))
        sys.stdout.flush()

        save_pickle(RSL_PATH, 'metaval_imax_intent_%s_%s.pkl'%(c,epoch), (v_macro_avg_eer, v_macro_avg_acc_ideal, v_macro_avg_acc))
        save_pickle(RSL_PATH, 'vprobs_gts_imax_intent_%s_%s.pkl'%(c,epoch), (v_probs, v_gts))

        v_eer_ += v_macro_avg_eer
        v_acc_ideal_ += v_macro_avg_acc_ideal
        v_acc_ += v_macro_avg_acc

        v_avg_conf_ood_ += v_avg_conf_ood
        v_gts_.extend(v_gts)
        v_probs_.extend(v_probs)

        
        t_macro_avg_eer, t_macro_avg_far, t_macro_avg_frr, \
        t_macro_avg_acc_ideal, t_macro_avg_acc, \
        test_output_info_list, domain_test, t_avg_conf_ood, t_probs, t_gts = compute_values_eval(params, experiment, test_dl, "test_dat")
     
        print("eer, onacc_ideal, onacc: %.3f, %.3f, %.3f" %
          (t_macro_avg_eer, 
           t_macro_avg_acc_ideal, 
           t_macro_avg_acc))
        sys.stdout.flush()


        save_pickle(RSL_PATH, 'metatest_imax_intent_%s_%s.pkl'%(c,epoch), (t_macro_avg_eer, t_macro_avg_acc_ideal, t_macro_avg_acc))
        save_pickle(RSL_PATH, 'tprobs_gts_imax_intent_%s_%s.pkl'%(c,epoch), (t_probs, t_gts))

       
        t_eer_ += t_macro_avg_eer
        t_acc_ideal_ += t_macro_avg_acc_ideal
        t_acc_ += t_macro_avg_acc

        t_avg_conf_ood_ += t_avg_conf_ood
        t_gts_.extend(t_gts)
        t_probs_.extend(t_probs)
        
        
    v_eer_ /= len(dev_set)
    v_acc_ideal_ /= len(dev_set)
    v_acc_ /= len(dev_set)

    v_avg_conf_ood_ /= len(dev_set)

    print("Meta-Valid Macro(eer, onacc_ideal, onacc): %.3f, %.3f, %.3f" %
          (v_eer_, 
           v_acc_ideal_, 
           v_acc_))
    sys.stdout.flush()

    v_probs_ = np.array(v_probs_)
    v_gts_ = np.array(v_gts_)

    save_pickle(RSL_PATH, 'metaval_imax_intent_all_%s.pkl'%epoch, (v_eer_, v_acc_ideal_, v_acc_))
    save_pickle(RSL_PATH, 'vprobs_gts_imax_intent_all_%s.pkl'%epoch, (v_probs_, v_gts_))

    t_eer_ /= len(test_set)
    t_acc_ideal_ /= len(test_set)
    t_acc_ /= len(test_set)

    t_avg_conf_ood_ /= len(test_set)

    print("Meta-Test Macro(eer, onacc_ideal, onacc): %.3f, %.3f, %.3f" %
          (t_eer_, 
           t_acc_ideal_, 
           t_acc_))
    sys.stdout.flush()
   

    t_probs_ = np.array(t_probs_)
    t_gts_ = np.array(t_gts_)


    save_pickle(RSL_PATH, 'metatest_imax_intent_all_%s.pkl'%epoch, (t_eer_, t_acc_ideal_, t_acc_))
    save_pickle(RSL_PATH, 'tprobs_gts_imax_intent_all_%s.pkl'%epoch, (t_probs_, t_gts_))


if __name__ == '__main__':


    parser = argparse.ArgumentParser(description="Evaluate ProtoInfoMax on intent classification.")
    parser.add_argument('-config', help="path to configuration file", 
                        default="./config")
    parser.add_argument('-section', help="the section name of the experiment")

    args = parser.parse_args()
    config_paths = [args.config]
    config_parser = configparser.SafeConfigParser()
    config_found = config_parser.read(config_paths)

    params = get_all_parameters(config_parser, args.section)
    params['model_string'] = args.section

    numpy.random.seed(params['seed'])
    random.seed(params['seed'])

    print('Parameters:', params)
    sys.stdout.flush()

    
    voc, w2v = load_w2v()
    word2idx, idx2word = read_pickle('/content/protoinfomax/data/', 'dict_idx2word_intent.pkl')

    params['vocabulary'] = word2idx
    params['voclist'] = idx2word
    params["wordvectors"] = w2v
    params["word2idx"] = word2idx
    params["idx2word"] = idx2word

    for ep in [0,10,20,30,40,50,60,'best']:

        model = GRUEncoder(params, w2v, len(voc))
        optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), 1e-3)

        if ep =='best':
            checkpoint = torch.load(os.path.join('/content/protoinfomax/results/', 'imax_intent_k100.best.pth'), map_location=lambda storage, loc: storage)
        else:
            checkpoint = torch.load(os.path.join('/content/protoinfomax/results/', 'imax_intent_k100_%s.pth'%ep), map_location=lambda storage, loc: storage)

        model.load_state_dict(checkpoint['state_dict'])

        optimizer.load_state_dict(checkpoint['optim_dict'])
        epoch = checkpoint['epoch']

        print(model)
        print("stored epoch:", epoch)

        experiment = RunExperiment(model, params)
        eval_model(params, model, experiment, optimizer, ep)
    