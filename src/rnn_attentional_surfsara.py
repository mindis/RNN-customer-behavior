
import tensorflow as tf
import numpy as np
import os
#from PhasedLSTMCell_v1 import *
#from PhasedLSTMCell import *
import time


def _seq_length(sequence):
    used = tf.sign(tf.reduce_max(tf.abs(sequence), reduction_indices=2))
    length = tf.reduce_sum(used, reduction_indices=1)
    length = tf.cast(length, tf.int32)
    return length

def _last_relevant(output, length):
    batch_size = tf.shape(output)[0]
    max_length = tf.shape(output)[1]
    out_size = int(output.get_shape()[2])
    index = tf.range(0, batch_size) * max_length + (length - 1)
    flat = tf.reshape(output, [-1, out_size])
    relevant = tf.gather(flat, index)

    return relevant
    
    
    
class RNN_dynamic:

    

    def __init__(self, parameters):
        #self.attentional_layer = 'hidden_state'
        #self.attentional_layer = 'input'
        #self.attentional_layer = 'embedding' #TODO: Try embedding lookup tensorflow and MLP
        #self.attentional_layer = 'embedding_lookup'
        #self.embedding_size = 32
        
        self.parameters = parameters
        
    def create_model(self):
        tf.reset_default_graph()

        # tf Graph input
        self.x = tf.placeholder("float", [None, self.parameters['seq_length'], self.parameters['n_input']], name='x')
        self.y = tf.placeholder("float", [None, self.parameters['n_output']], name='y')

        # Define weights
        weights = {
            'alphas': tf.Variable(tf.random_normal([self.parameters['n_hidden'], 1]))
        }
        
        if self.parameters['attentional_layer'] == 'hidden_state':
            weights['out'] = tf.Variable(tf.random_normal([self.parameters['n_hidden'], self.parameters['n_output']]))
        elif self.parameters['attentional_layer'] == 'input':
            weights['out'] = tf.Variable(tf.random_normal([self.parameters['n_input'], self.parameters['n_output']]))
        elif self.parameters['attentional_layer'] == 'embedding':
            weights['out'] = tf.Variable(tf.random_normal([self.parameters['embedding_size'], self.parameters['n_output']]))
            weights['emb']   = tf.Variable(tf.random_normal([self.parameters['n_input'], self.parameters['embedding_size']]))
            
        biases = {
            'out': tf.Variable(tf.random_normal([self.parameters['n_output']])),
            'alphas': tf.Variable(tf.random_normal([1]))
            #'alphas': tf.Variable(tf.random_normal([self.parameters['seq_length']]))
        }


        # Define a lstm cell with tensorflow
        if self.parameters['rnn_type'].lower() == 'lstm':
            rnn_cell = tf.contrib.rnn.BasicLSTMCell(self.parameters['n_hidden'], forget_bias=1.0)
        elif self.parameters['rnn_type'].lower() == 'gru':
            rnn_cell = tf.contrib.rnn.GRUCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'lstm2':
            rnn_cell = tf.contrib.rnn.LSTMCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'rnn':
            rnn_cell = tf.contrib.rnn.BasicRNNCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'plstm':
            rnn_cell = PhasedLSTMCell(self.parameters['n_hidden'], use_peepholes=True, state_is_tuple=True)

                
        #Add dropout
        if self.parameters['dropout'] > 0:
            keep_prob = 1 - self.parameters['dropout']
            rnn_cell = tf.contrib.rnn.DropoutWrapper(rnn_cell, input_keep_prob=keep_prob, output_keep_prob=keep_prob)
            
            
        if self.parameters['rnn_layers'] > 1:
            rnn_cell = tf.contrib.rnn.MultiRNNCell([rnn_cell] * self.parameters['rnn_layers'])  
            
        if self.parameters['attentional_layer'] == 'embedding':   
            self.x_reshaped = tf.reshape(self.x, [-1, int(self.x.get_shape()[2])])
            v = tf.matmul(self.x_reshaped, weights['emb'])
            v_reshaped = tf.reshape(v, [-1, self.parameters['seq_length'], self.parameters['embedding_size']])
            outputs, states = tf.nn.dynamic_rnn(
                rnn_cell,
                v_reshaped,
                dtype=tf.float32,
                sequence_length=_seq_length(v_reshaped)
            )
        else:
            outputs, states = tf.nn.dynamic_rnn(
                rnn_cell,
                self.x,
                dtype=tf.float32,
                sequence_length=_seq_length(self.x)
            )


        
        self.outputs = outputs
        self.weights = weights
        self.biases = biases
        #Obtain ej
        batch_shape = outputs.get_shape()[0]
        batch_per_seq_length_shape = batch_shape * outputs.get_shape()[1]
        self.outputs_reshaped = tf.reshape(outputs, [-1, int(outputs.get_shape()[2])])
        print('--------------------')
        print('weights out:')
        print(weights['out'].get_shape())
        print('outputs:')
        print(outputs.get_shape())
        print('weights alphas:')
        print(weights['alphas'].get_shape())
        print('self.outputs_reshaped:')
        print(self.outputs_reshaped.get_shape())
        print('biases[alphas]:')
        print(biases['alphas'].get_shape())
        print('--------------------')
        self.ejs = tf.matmul(self.outputs_reshaped, weights['alphas']) + biases['alphas'] #Check
        print('self.ejs:')
        print(self.ejs.get_shape())
        
        
        #Obtain attention weights alphas
        self.ejs_reshaped = tf.reshape(self.ejs, [-1, int(outputs.get_shape()[1])])
        self.alphas = tf.nn.softmax(self.ejs_reshaped) 
        self.reshaped_alphas = tf.reshape(self.alphas, [-1, 1])
        
        #Obtain context vector c
        if self.parameters['attentional_layer'] == 'hidden_state':
            self.context = self.reshaped_alphas * self.outputs_reshaped #TODO: Try also to multiply with input (or embedding as they do in the paper)
        elif self.parameters['attentional_layer'] == 'input':
            self.x_reshaped = tf.reshape(self.x, [-1, int(self.x.get_shape()[2])])
            self.context = self.reshaped_alphas * self.x_reshaped
        elif self.parameters['attentional_layer'] == 'embedding':
            self.context = self.reshaped_alphas * v
        self.context_reshaped = tf.reshape(self.context, [-1, self.parameters['seq_length'], int(self.context.get_shape()[1])])
        self.context_reduced = tf.reduce_sum(self.context_reshaped, axis= 1)
        
        
        #Obtaining the correct output state
        #if self.parameters['padding'].lower() == 'right': #If padding zeros is at right, we need to get the right output, since the last is not validation
            #self.last_relevant_output = _last_relevant(outputs, _seq_length(self.x))
        #elif self.parameters['padding'].lower() == 'left':
            #self.last_relevant_output = outputs[:,-1,:]
        #logits = tf.matmul(self.last_relevant_output, weights['out']) + biases['out']
        
        logits = tf.matmul(self.context_reduced, weights['out']) + biases['out']


        
        #self._debug = logits
        #self._debug = outputs

        if self.parameters['type_output'].lower() == 'sigmoid':
            self.pred_prob = tf.sigmoid(logits)
            self.loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=logits, labels=self.y))
        else:
            self.pred_prob = tf.nn.softmax(logits)
            self.loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=self.y))

        #Add L2 regularizatoin loss
        self.loss = self.loss + self.parameters['l2_reg'] * tf.nn.l2_loss(weights['out'])

        #Define optimizer
        if self.parameters['opt'].lower() == 'sgd':
            self.optimizer = tf.train.GradientDescentOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'adam':
            self.optimizer = tf.train.AdamOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'adadelta':
            self.optimizer = tf.train.AdadeltaOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'adagrad':
            self.optimizer = tf.train.AdagradOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'adagraddao':
            self.optimizer = tf.train.AdagradDAOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'momentum':
            self.optimizer = tf.train.MomentumOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'ftrl':
            self.optimizer = tf.train.FtrlOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'proximalgd':
            self.optimizer = tf.train.ProximalGradientDescentOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'proximaladagrad':
            self.optimizer = tf.train.ProximalAdagradOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        elif self.parameters['opt'].lower() == 'rms':
            self.optimizer = tf.train.RMSPropOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.loss)
        


        # Accuracy (Find a better evaluation)
        class_predictions = tf.cast(self.pred_prob > 0.5, tf.float32)
        correct_pred = tf.equal(class_predictions, self.y)
        self.accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))
        #correct_pred = tf.equal(tf.argmax(pred,1), tf.argmax(y,1))
        #accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

        #MAP
        num_samples = tf.shape(self.y)[0]
        cut_at_k = 7
        mask_vector = np.zeros(self.parameters['n_output'])
        mask_vector[:cut_at_k] = 1
        sorted_pred_ind = tf.nn.top_k(self.pred_prob, self.parameters['n_output'], sorted=True)[1]
        shape_ind = tf.shape(sorted_pred_ind)
        auxiliary_indices = tf.meshgrid(*[tf.range(d) for d in (tf.unstack(shape_ind[:(sorted_pred_ind.get_shape().ndims - 1)]) + [self.parameters['n_output']])], indexing='ij')
        t_sort_prod = tf.gather_nd(self.y, tf.stack(auxiliary_indices[:-1] + [sorted_pred_ind], axis=-1))

        num_added = tf.reduce_sum(t_sort_prod, axis=1)
        cumsum = tf.cumsum(t_sort_prod, axis=1)
        #repeat = tf.constant(np.repeat( (np.arange(self.parameters['n_output']) + 1).reshape(1, self.parameters['n_output']), y, axis=0))
        repeat = tf.reshape( (tf.range(self.parameters['n_output']) + 1), [1, -1])
        repeat = tf.tile(repeat, [tf.shape(self.y)[0], 1])
        p_at_k = tf.cast(cumsum, tf.float32)/tf.cast(repeat, tf.float32)

        mask_at_k = tf.reshape(mask_vector, [1, -1])
        mask_at_k = tf.tile(mask_at_k, [tf.shape(self.y)[0], 1])
        #mask_at_k = tf.constant(np.repeat(mask_vector.reshape(1, self.parameters['n_output']), num_samples, axis=0))


        sum_p_at_k = tf.reduce_sum((tf.cast(p_at_k, tf.float32) * tf.cast(mask_at_k, tf.float32)),  axis=1)
        t_cut = tf.fill((1, num_samples), cut_at_k)
        num_added_cut_k = tf.minimum(tf.cast(t_cut, tf.float32), tf.cast(num_added, tf.float32))
        num_added_cut_k = tf.maximum(num_added_cut_k, tf.cast(tf.fill((1, num_samples), 1), tf.float32))
        #AP = tf.cast(sum_p_at_k, tf.float32)/tf.cast(num_added_cut_k, tf.float32)
        AP = tf.cast(sum_p_at_k, tf.float32)/tf.cast(cut_at_k, tf.float32)
        self.MAP = tf.reduce_mean(AP)
        
        #Add summaries
        tf.summary.scalar('MAP', self.MAP)
        tf.summary.scalar('loss', self.loss)
        tf.summary.scalar('accuracy', self.accuracy)
        
        
        self.init = tf.global_variables_initializer()
        
    def train(self, ds):
    
        #Optimize
        display_step = 10
        checkpoint_freq_step = 20
        #max_steps = 30000000
        #max_steps = 600000
        # Create a saver.
        saver = tf.train.Saver()
        self.parameters_str = str('rep' + str(ds._representation) + '-' + self.parameters['rnn_type']) + '-' + str(self.parameters['n_hidden']) + '-' + str(self.parameters['rnn_layers']) + '-' + str(self.parameters['batch_size']) + '-' + str(self.parameters['opt']) + '-' + str(self.parameters['max_steps'])
        self.parameters_str += '-' + time.strftime("%Y%m%d-%H%M%S")
        checkpoint_dir = './checkpoints/' + self.parameters_str
        if not tf.gfile.Exists(checkpoint_dir):
            tf.gfile.MakeDirs(checkpoint_dir)
            tf.gfile.MakeDirs(checkpoint_dir + '/best_model')
            tf.gfile.MakeDirs(checkpoint_dir + '/last_model')
        self.best_loss = 150000000
        # Launch the graph
        with tf.Session() as sess:
            merged = tf.summary.merge_all()
            train_writer = tf.summary.FileWriter('tensorboard/Santander/' + str(self.parameters_str) + '/train', sess.graph)
            train_last_month_writer = tf.summary.FileWriter('tensorboard/Santander/' + str(self.parameters_str) + '/train_last_month', sess.graph)
            val_writer = tf.summary.FileWriter('tensorboard/Santander/' + str(self.parameters_str) + '/val', sess.graph)
            test_writer = tf.summary.FileWriter('tensorboard/Santander/' + str(self.parameters_str) + '/test', sess.graph)
            sess.run(self.init)

            step = 1
            
            # Keep training until reach max iterations
            while step * self.parameters['batch_size'] < self.parameters['max_steps']:
                total_iterations = step * self.parameters['batch_size']
                
                #Obtain batch for this iteration
                batch_x, batch_y = ds.next_batch(self.parameters['batch_size'])
                '''
                print('Start')
                outputs, weights, biases = sess.run([self.outputs, self.weights, self.biases], feed_dict={self.x: batch_x, self.y: batch_y})
                print(outputs)
                print(weights['alphas'].shape)
                #print(weights)
                #print(biases)
                
                outputs_reshaped = sess.run([self.outputs_reshaped], feed_dict={self.x: batch_x, self.y: batch_y})
                print('weights[alphas]: ' + str(weights['alphas'][0].shape))
                print(weights['alphas'])
                
                outputs_reshaped = sess.run([self.outputs_reshaped], feed_dict={self.x: batch_x, self.y: batch_y})
                print('outputs_reshaped: ' + str(outputs_reshaped[0].shape))
                print(outputs_reshaped)
                
                
                ejs = sess.run([self.ejs], feed_dict={self.x: batch_x, self.y: batch_y})
                print('ejs: ' + str(ejs[0].shape))
                print(ejs)
                
                
                
                ejs_reshaped = sess.run([self.ejs_reshaped], feed_dict={self.x: batch_x, self.y: batch_y})
                print('ejs_reshaped: '  + str(ejs_reshaped[0].shape))
                print(ejs_reshaped)
                
                
                alphas = sess.run([self.alphas], feed_dict={self.x: batch_x, self.y: batch_y})
                print('alphas: '  + str(alphas[0].shape))
                print(alphas)
                
                reshaped_alphas = sess.run([self.reshaped_alphas], feed_dict={self.x: batch_x, self.y: batch_y})
                print('reshaped_alphas: '  + str(reshaped_alphas[0].shape))
                print(reshaped_alphas)
                
                
                context = sess.run([self.context], feed_dict={self.x: batch_x, self.y: batch_y})
                print('context: ' + str(context[0].shape))
                print(context)
                
                
                context_reshaped = sess.run([self.context_reshaped], feed_dict={self.x: batch_x, self.y: batch_y})
                print('context_reshaped: ' + str(context_reshaped[0].shape))
                print(context_reshaped)
                
                context_reduced = sess.run([self.context_reduced], feed_dict={self.x: batch_x, self.y: batch_y})
                print('context_reduced: ' + str(context_reduced[0].shape))
                print(context_reduced)
                break
                '''

                
                # Run optimization op (backprop)
                sess.run(self.optimizer, feed_dict={self.x: batch_x, self.y: batch_y})
                _, c = sess.run([self.optimizer, self.loss],
                                             feed_dict={self.x: batch_x, self.y: batch_y})
                
                if (step % display_step == 0) or ((total_iterations + self.parameters['batch_size'])  >= (self.parameters['max_steps'] - 1)):
                    print('------------------------------------------------')
                    # Calculate batch loss
                    train_minibatch_loss, summary = sess.run([self.loss, merged], feed_dict={self.x: batch_x, self.y: batch_y})
                    print("Iter " + str(total_iterations) + ", Minibatch train Loss= " + 
                          "{:.6f}".format(train_minibatch_loss))
                    train_writer.add_summary(summary, total_iterations)
                    # Calculate training loss at last month
                    train_last_month_loss, train_last_month_accuracy, train_last_month_map, summary = sess.run([self.loss, self.accuracy, self.MAP, merged], feed_dict={self.x: ds._X_train_last_month, self.y: ds._Y_train_last_month})
                    print("Iter " + str(total_iterations) + ", Last month train Loss= " + 
                          "{:.6f}".format(train_last_month_loss) + ", Last month train Accuracy= " + 
                          "{:.6f}".format(train_last_month_accuracy) + ", Last train Map= " + 
                          "{:.6f}".format(train_last_month_map))
                    train_last_month_writer.add_summary(summary, total_iterations)
                    # Calculate val loss
                    self.val_loss, val_acc, val_map, summary = sess.run([self.loss, self.accuracy, self.MAP, merged], feed_dict={self.x:ds._X_val, self.y:ds._Y_val})
                    val_writer.add_summary(summary, total_iterations)
                    print("Iter " + str(total_iterations) + ", Validation  Loss= " + 
                          "{:.6f}".format(self.val_loss) + ", Validation  Accuracy= " + 
                          "{:.6f}".format(val_acc) + ", Validation Map= " + 
                          "{:.6f}".format(val_map))
                    # Calculate test loss
                    self.test_loss, test_acc, test_map, summary = sess.run([self.loss, self.accuracy, self.MAP, merged], feed_dict={self.x:ds._X_local_test, self.y:ds._Y_local_test})
                    test_writer.add_summary(summary, total_iterations)
                    print("Iter " + str(total_iterations) + ", Test Loss= " + 
                          "{:.6f}".format(self.test_loss) + ", Test Accuracy= " + 
                          "{:.6f}".format(test_acc) + ", Test Map= " + 
                          "{:.6f}".format(test_map))

                    
                    #If best loss save the model as best model so far
                    if self.val_loss < self.best_loss:
                        self.best_loss = self.val_loss
                        checkpoint_dir_tmp = checkpoint_dir + '/best_model/'
                        checkpoint_path = os.path.join(checkpoint_dir_tmp, 'model_best.ckpt')
                        saver.save(sess, checkpoint_path, global_step=total_iterations)
                        self.best_model_path = 'model_best.ckpt-' + str(total_iterations)
                        #print('-->save best model: ' + str(checkpoint_path) + ' - step: ' + str(step) + ' best_model_path: ' + str(self.best_model_path))
                    print('------------------------------------------------')
                    
                    
                #Save check points periodically or in last iteration
                if (step % checkpoint_freq_step == 0) or ( (total_iterations + self.parameters['batch_size'])  >= (self.parameters['max_steps'] - 1)):
                    checkpoint_dir_tmp =  checkpoint_dir + '/last_model/'
                    checkpoint_path = os.path.join(checkpoint_dir_tmp, 'last_model.ckpt')
                    saver.save(sess, checkpoint_path, global_step=total_iterations)
                    self.last_model_path = 'last_model.ckpt-' + str(total_iterations)
                    #print('-->save checkpoint model: ' + str(checkpoint_path) + ' - step: ' + str(step) + ' last_model_path: ' + str(self.last_model_path))
                    
                step += 1
            print("Optimization Finished!")
            
            
            #pred_val = sess.run(self.pred_prob, feed_dict={self.x: ds._X_val})
            # Calculate val loss
            #self.val_loss, val_acc, val_map = sess.run([self.loss, self.accuracy, self.MAP], feed_dict={self.x: ds._X_val, self.y: ds._Y_val})
            #print('Final validation loss: ' + str(self.val_loss) + ', Validation accuracy: ' + str(val_acc) + ', Validation MAP: ' + str(val_map))
            
    def predict(self, X_test):
        #Make predictions for test set with the best model
        checkpoint_dir = './checkpoints/' + self.parameters_str
        saver = tf.train.Saver()

        #CHECK: is removing the best model sometimes
        if self.best_loss < self.val_loss:
            checkpoint_dir_tmp =  checkpoint_dir + '/best_model/'
            checkpoint_path = os.path.join(checkpoint_dir_tmp, self.best_model_path)
        else:
            checkpoint_dir_tmp =  checkpoint_dir + '/last_model/'
            checkpoint_path = os.path.join(checkpoint_dir_tmp, self.last_model_path)


        
        #checkpoint_path = os.path.join(checkpoint_dir, self.last_model_path)
        with tf.Session() as sess:
            saver.restore(sess, checkpoint_path)
            

            #pred_test = []
            pred_test = np.zeros((len(X_test), self.parameters['n_output']))
            num_test_splits = 5 #Split to fit in memory when using large network architectures
            test_split_size = int(len(X_test)/num_test_splits)
            for i in range(num_test_splits):
                initial_idx = i * test_split_size
                final_idx = (i+1) * test_split_size
                print('Initial index: ' + str(initial_idx))
                print('final_idx index: ' + str(final_idx))
                if i < (num_test_splits - 1):
                    pred_test_split = sess.run(self.pred_prob, feed_dict={self.x: X_test[initial_idx:final_idx]})
                    print(pred_test_split.shape)
                    pred_test[initial_idx:final_idx] = pred_test_split
                else:
                    pred_test_split = sess.run(self.pred_prob, feed_dict={self.x: X_test[initial_idx:]})
                    print(pred_test_split.shape)
                    pred_test[initial_idx:] = pred_test_split
                #pred_test.append(pred_test_split)
                
            #pred_test = sess.run(self.pred_prob, feed_dict={x: X_test})

            #print(pred_test[0].shape)
            #pred_test = np.array(pred_test)
            #print(pred_test.shape)
            #pred_test = pred_test.reshape((len(X_test), self.parameters['n_output']))
        
        return pred_test
        
    def get_last_hidden_state(self, X_test):
        #Make predictions for test set with the best model
        checkpoint_dir = './checkpoints'
        saver = tf.train.Saver()

        #CHECK: is removing the best model sometines
        if self.best_loss < self.val_loss:
            checkpoint_path = os.path.join(checkpoint_dir, self.best_model_path)
            print('load best model: ' + str(checkpoint_path))
        else:
            checkpoint_path = os.path.join(checkpoint_dir, self.last_model_path)
            print('load last model' + str(checkpoint_path))
        
        
        checkpoint_path = os.path.join(checkpoint_dir, self.last_model_path)
        with tf.Session() as sess:
            saver.restore(sess, checkpoint_path)
            last_hidden_state = sess.run(self.last_relevant_output, feed_dict={self.x: X_test})

            
        
        return last_hidden_state