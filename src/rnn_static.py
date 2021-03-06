
import tensorflow as tf
import numpy as np
import os

def _seq_length(sequence):
    used = tf.sign(tf.reduce_max(tf.abs(sequence), reduction_indices=2))
    length = tf.reduce_sum(used, reduction_indices=1)
    length = tf.cast(length, tf.int32)
    return length


class RNN_static:

    def __init__(self, parameters):

        self.parameters = parameters

    

    #Select the Last Relevant Output
    def _last_relevant(self, output, length):
        batch_size = tf.shape(output)[0]
        max_length = tf.shape(output)[1]
        out_size = int(output.get_shape()[2])
        index = tf.range(0, batch_size) * max_length + (length - 1)
        flat = tf.reshape(output, [-1, out_size])
        relevant = tf.gather(flat, index)

        return relevant
        
        
    def RNN(self, x, weights, biases):

        


        # Define a lstm cell with tensorflow
        if self.parameters['rnn_type'].lower() == 'lstm':
            rnn_cell = tf.nn.rnn_cell.BasicLSTMCell(self.parameters['n_hidden'], forget_bias=1.0)
        elif self.parameters['rnn_type'].lower() == 'gru':
            rnn_cell = tf.nn.rnn_cell.GRUCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'lstm2':
            rnn_cell = tf.nn.rnn_cell.LSTMCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'rnn':
            rnn_cell = tf.nn.rnn_cell.BasicRNNCell(self.parameters['n_hidden'])
        elif self.parameters['rnn_type'] == 'lstm3':
            rnn_cell = tf.nn.rnn_cell.LayerNormBasicLSTMCell(self.parameters['n_hidden'], dropout_keep_prob=0.9, dropout_prob_seed=17)
        elif self.parameters['rnn_type'] == 'lstm4':
            rnn_cell = tf.nn.rnn_cell.CoupledInputForgetGateLSTMCell(self.parameters['n_hidden'], use_peepholes=False) #https://www.tensorflow.org/api_docs/python/tf/contrib/rnn/CoupledInputForgetGateLSTMCell
        
        #Add dropout
        if self.parameters['dropout'] > 0:
            keep_prob = 1 - self.parameters['dropout']
            rnn_cell = tf.nn.rnn_cell.DropoutWrapper(rnn_cell, input_keep_prob=keep_prob, output_keep_prob=keep_prob)
        
        #stack rnn cells
        if self.parameters['rnn_layers'] > 1:
            #cell = tf.nn.rnn_cell.DropoutWrapper(cell, output_keep_prob=self._dropout_placeholder)
            rnn_cell = tf.nn.rnn_cell.MultiRNNCell([rnn_cell] * self.parameters['rnn_layers'])
        
        #TODO: Residual Wrappers: https://www.tensorflow.org/versions/master/api_docs/python/contrib.rnn/core_rnn_cell_wrappers__rnncells_that_wrap_other_rnncells_#ResidualWrapper
        
        
        # Get lstm cell output
        #tf.nn.rnn(cell, inputs,#initial_state=self._initial_state)
        #outputs, states = tf.contrib.rnn.static_rnn(lstm_cell, x, dtype=tf.float32)

        if self.parameters['padding'].lower() == 'left':
            # Prepare data shape to match `rnn` function requirements
            # Current data input shape: (batch_size, n_steps, n_input)
            # Required shape: 'n_steps' tensors list of shape (batch_size, n_input)
            
            # Permuting batch_size and n_steps            
            x = tf.transpose(x, [1, 0, 2])          
            
            # Reshaping to (n_steps*batch_size, n_input)
            x = tf.reshape(x, [-1, self.parameters['n_input']])
            
            # Split to get a list of 'n_steps' tensors of shape (batch_size, n_input)
            #x = tf.split(x, n_steps, 0)
            x = tf.split(split_dim=0, num_split=self.parameters['seq_length'], value=x)
        
            outputs, states = tf.nn.rnn(rnn_cell, x, dtype=tf.float32)
        elif self.parameters['padding'].lower() == 'right':
            #x = tf.placeholder(tf.float32, [None, max_length, frame_size])
            outputs, states = tf.nn.dynamic_rnn(
            rnn_cell,
            self.x,
            dtype=tf.float32,
            sequence_length=_seq_length(self.x)
            )

        
        #Obtaining the correct output state
        if self.parameters['padding'].lower() == 'right': #If padding zeros is at right, we need to get the right output, since the last is not validation
            last_relevant_output = self._last_relevant(outputs, _seq_length(self.x))
        elif self.parameters['padding'].lower() == 'left':
            last_relevant_output = outputs[-1]
        
 

        # Linear activation, using rnn inner loop last output
        return tf.matmul(last_relevant_output, weights['out']) + biases['out']

    def create_model(self):
        tf.reset_default_graph()

        # tf Graph input
        self.x = tf.placeholder("float", [None, self.parameters['seq_length'], self.parameters['n_input']], name='x')
        self.y = tf.placeholder("float", [None, self.parameters['n_output']], name='y')

        # Define weights
        weights = {
            'out': tf.Variable(tf.random_normal([self.parameters['n_hidden'], self.parameters['n_output']]))
        }
        biases = {
            'out': tf.Variable(tf.random_normal([self.parameters['n_output']]))
        }

        pred = self.RNN(self.x, weights, biases)

        # Define loss 
        
            

        if self.parameters['type_output'].lower() == 'sigmoid':
            self.pred_prob = tf.sigmoid(pred)
            self.cost = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(pred, self.y))
        else:
            self.pred_prob = tf.nn.softmax(pred)
            self.cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(pred, self.y))
        ''' Maybe something like this should be used for padding right
            def cost(output, target):
            # Compute cross entropy for each frame.
            cross_entropy = target * tf.log(output)
            cross_entropy = -tf.reduce_sum(cross_entropy, reduction_indices=2)
            mask = tf.sign(tf.reduce_max(tf.abs(target), reduction_indices=2))
            cross_entropy *= mask
            # Average over actual sequence lengths.
            cross_entropy = tf.reduce_sum(cross_entropy, reduction_indices=1)
            cross_entropy /= tf.reduce_sum(mask, reduction_indices=1)
            return tf.reduce_mean(cross_entropy)
        '''
        
        #Add L2 regularizatoin loss
        self.cost = self.cost + self.parameters['l2_reg'] * tf.nn.l2_loss(weights['out'])
        
        #Define optimizer
        if self.parameters['opt'].lower() == 'sgd':
            self.optimizer = tf.train.GradientDescentOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'adam':
            self.optimizer = tf.train.AdamOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'adadelta':
            self.optimizer = tf.train.AdadeltaOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'adagrad':
            self.optimizer = tf.train.AdagradOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'adagraddao':
            self.optimizer = tf.train.AdagradDAOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'momentum':
            self.optimizer = tf.train.MomentumOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'ftrl':
            self.optimizer = tf.train.FtrlOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'proximalgd':
            self.optimizer = tf.train.ProximalGradientDescentOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'proximaladagrad':
            self.optimizer = tf.train.ProximalAdagradOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
        elif self.parameters['opt'].lower() == 'rms':
            self.optimizer = tf.train.RMSPropOptimizer(learning_rate=self.parameters['learning_rate']).minimize(self.cost)
            
            
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
        
        
        
        
        # Initializing the variables
        self.init = tf.global_variables_initializer()

        
    def train(self, ds):
        
        
        #Optimize
        display_step = 100
        checkpoint_freq_step = 100
        #max_steps = 30000000
        #max_steps = 600000
        # Create a saver.
        saver = tf.train.Saver()
        checkpoint_dir = './checkpoints'
        self.best_loss = 150000000
        # Launch the graph
        with tf.Session() as sess:
            sess.run(self.init)

            step = 1
            # Keep training until reach max iterations
            while step * self.parameters['batch_size'] < self.parameters['max_steps']:
            #while ds._epochs_completed < 10:
                batch_x, batch_y = ds.next_batch(self.parameters['batch_size'])
                # Run optimization op (backprop)
                sess.run(self.optimizer, feed_dict={self.x: batch_x, self.y: batch_y})
                _, c = sess.run([self.optimizer, self.cost],
                                             feed_dict={self.x: batch_x, self.y: batch_y})
                
                if step % display_step == 0:
                    # Calculate batch loss
                    loss = sess.run(self.cost, feed_dict={self.x: batch_x, self.y: batch_y})
                    print("Iter " + str(step*self.parameters['batch_size']) + ", Minibatch train Loss= " + 
                          "{:.6f}".format(loss))
                    # Calculate val loss
                    self.val_loss, val_acc, val_map = sess.run([self.cost, self.accuracy, self.MAP], feed_dict={self.x:ds._X_val, self.y:ds._Y_val})
                    print('Val loss: ' + str(self.val_loss) + ', Val accuracy: ' + str(val_acc) + ', Val MAP: ' + str(val_map))
                    if self.val_loss < self.best_loss:
                        self.best_loss = self.val_loss
                        checkpoint_path = os.path.join(checkpoint_dir, 'model_best.ckpt')
                        saver.save(sess, checkpoint_path, global_step=step)
                        #TODO save best path to load it later
                        self.best_model_path = 'model_best.ckpt-' + str(step)
                        #print('-->save best model: ' + str(checkpoint_path) + ' - step: ' + str(step) + ' best_model_path: ' + str(self.best_model_path))
                    
                if (step % checkpoint_freq_step == 0) or (step == self.parameters['max_steps'] - 1):
                    checkpoint_path = os.path.join(checkpoint_dir, 'model_last.ckpt')
                    saver.save(sess, checkpoint_path, global_step=step)
                    self.last_model_path = 'model_last.ckpt-' + str(step)
                    #print('-->save checkpoint model: ' + str(checkpoint_path) + ' - step: ' + str(step) + ' last_model_path: ' + str(self.last_model_path))
                    
                step += 1
            print("Optimization Finished!")
            
            
            pred_val = sess.run(self.pred_prob, feed_dict={self.x: ds._X_val})
            # Calculate val loss
            self.val_loss, val_acc, val_map = sess.run([self.cost, self.accuracy, self.MAP], feed_dict={self.x: ds._X_val, self.y: ds._Y_val})
            print('Final validation loss: ' + str(self.val_loss) + ', Validation accuracy: ' + str(val_acc) + ', Validation MAP: ' + str(val_map))
            
            
    def predict(self, X_test):
        #Make predictions for test set with the best model
        checkpoint_dir = './checkpoints'
        saver = tf.train.Saver()

        ''' FIX: is removing the best model sometines
        if self.best_loss < self.val_loss:
            checkpoint_path = os.path.join(checkpoint_dir, self.best_model_path)
            print('load best model: ' + str(checkpoint_path))
        else:
            checkpoint_path = os.path.join(checkpoint_dir, self.last_model_path)
            print('load last model' + str(checkpoint_path))
        '''
        checkpoint_path = os.path.join(checkpoint_dir, self.last_model_path)
        with tf.Session() as sess:
            saver.restore(sess, checkpoint_path)
            

            pred_test = []
            num_test_splits = 5 #Split to fit in memory when using large network architectures
            test_split_size = int(len(X_test)/num_test_splits)
            for i in range(num_test_splits):
                initial_idx = i * test_split_size
                final_idx = (i+1) * test_split_size
                print('Initial index: ' + str(initial_idx))
                print('final_idx index: ' + str(final_idx))
                if i < (num_test_splits - 1):
                    pred_test_split = sess.run(self.pred_prob, feed_dict={self.x: X_test[initial_idx:final_idx]})
                else:
                    pred_test_split = sess.run(self.pred_prob, feed_dict={self.x: X_test[initial_idx:]})
                pred_test.append(pred_test_split)
            #pred_test = sess.run(self.pred_prob, feed_dict={x: X_test})

            print(pred_test[0].shape)
            pred_test = np.array(pred_test)
            print(pred_test.shape)
            pred_test = pred_test.reshape((len(X_test), self.parameters['n_output']))
        
        return pred_test
