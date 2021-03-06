import scipy
from scipy import stats
import numpy as np
import tensorflow as tf
import os
import time
import sys
import pickle
from rnn_dynamic import *
#from rnn_attentional import * #For the attentional experiment
from scipy import spatial

def sign_test(a, b):
    b_minus_a = b - a
    sign_b_minus_a = np.sign(b_minus_a)
    num_successes = np.sum(sign_b_minus_a == 1)
    num_trials = len(b_minus_a) - np.sum(sign_b_minus_a == 0)

    print('B is better than A in ' + str(num_successes) + ' of ' + str(num_trials))

    hh = scipy.stats.binom(num_trials, 0.5)

    p_value = 0
    for k in range(num_successes, num_trials + 1):
        p_value += hh.pmf(k)

    return p_value

#H0: both measure are not different
#H1: Measure 2 better than 1

measure = 'spss'
methods = ['RQ1_1', 'RQ1_2', 'RQ1_3a', 'RQ1_3b', 'RQ1_4', 'RQ1_5', 'RQ2_1a', 'RQ2_1b', 'RQ2_2a', 'RQ2_2b']

for i in range(len(methods)):
    for j in range(i+1, len(methods)):
        method_1 = methods[i]
        method_2 = methods[j]
        path_measure_1 = 'pickles/movielens/measures/final_measures/' + measure + '_' + method_1 + '_Final.pickle'
        path_measure_2 = 'pickles/movielens/measures/final_measures/' + measure + '_' + method_2 + '_Final.pickle'

        # path_measure_1 = 'pickles/movielens/measures/precision_r_RQ1_4.pickle'
        # path_measure_2 = 'pickles/movielens/measures/precision_r_RQ1_3a.pickle'

        with open(path_measure_1, 'rb') as handle:
            measure_1 = pickle.load(handle)
        with open(path_measure_2, 'rb') as handle:
            measure_2 = pickle.load(handle)

        if isinstance(measure_1, list):
            measure_1 = np.array(measure_1)
        if isinstance(measure_2, list):
            measure_2 = np.array(measure_2)

        # Test
        # measure_1 = np.array([0.25, 0.43, 0.39, 0.75, 0.43, 0.15, 0.20, 0.52, 0.49, 0.50])
        # measure_2 = np.array([0.35, 0.84, 0.15, 0.75, 0.68, 0.85, 0.80, 0.50, 0.58, 0.75])

        #print('Some samples')
        #print('measure 1: ' + str(measure_1[0:10]))
        #print('measure 2: ' + str(measure_2[0:10]))

        p_value = sign_test(measure_1, measure_2)

        print('p-value measure ' + method_2 + ' is better than ' + method_2 + ': ' + str(p_value))

        wilcoxon = scipy.stats.wilcoxon(measure_1, measure_2)
        print('Wilcoxon test with ' + method_1 + ' vs ' + method_2 + ': ' + str(wilcoxon))
        print('----------------')