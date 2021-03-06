import numpy as np
import torch.utils.data as data
from torch.utils.data.sampler import BatchSampler
import os
import random
import sidekit
import torch
import re

class BalancedBatchSampler(BatchSampler):
    """
    BatchSampler - from a MNIST-like dataset, samples n_classes and within these classes samples n_samples.
    Returns batches of size n_classes * n_samples
    """

    def __init__(self, labels, n_classes, n_samples): # 这是针对整个数据集来说的
        self.labels = labels
        self.labels_set = list(set(self.labels.numpy()))
        self.label_to_indices = {label: np.where(self.labels.numpy() == label)[0]
                                 for label in self.labels_set} # label : index
        for l in self.labels_set:
            np.random.shuffle(self.label_to_indices[l]) # 打乱顺序
        self.used_label_indices_count = {label: 0 for label in self.labels_set}
        self.count = 0
        self.n_classes = n_classes
        self.n_samples = n_samples
        self.n_dataset = len(self.labels)
        self.batch_size = self.n_samples * self.n_classes # 返回的total sample numbers

    def __iter__(self):
        self.count = 0
        while self.count + self.batch_size < self.n_dataset:
            classes = np.random.choice(self.labels_set, self.n_classes, replace=False) # 随机选择n_classes的label
            indices = []
            for class_ in classes:
                indices.extend(self.label_to_indices[class_][
                               self.used_label_indices_count[class_]:self.used_label_indices_count[
                                                                         class_] + self.n_samples])
                self.used_label_indices_count[class_] += self.n_samples
                if self.used_label_indices_count[class_] + self.n_samples > len(self.label_to_indices[class_]):
                    np.random.shuffle(self.label_to_indices[class_])
                    self.used_label_indices_count[class_] = 0 # 如果超过了范围就置零重新生成
            yield indices # 返回indices
            self.count += self.n_classes * self.n_samples

    def __len__(self):
        return self.n_dataset // self.batch_size # 返回的是迭代的次数

def fixed_length(array, max_length):
    x = []
    for i in range(array.shape[0]):
        if array[i].shape[0] >= max_length:
            # too long, we slice
            a = random.randrange(array[i].shape[0] - max_length + 1)
            b = a + max_length
            sliced = array[i][a:b, :]
            sliced = np.roll(sliced, random.randrange(max_length), axis=0)
            x.append(sliced)
        else:
            # too short, we pad
            pad_width = ((0, max_length - array[i].shape[0]), (0,0))
            padded = np.pad(array[i], pad_width, 'wrap')
            padded = np.roll(padded, random.randrange(max_length), axis=0)
            x.append(padded)
    return np.array(x) 

class DeepSpkDataset(data.Dataset):
    def __init__(self, path, maxlen):
        super(DeepSpkDataset, self).__init__()
        pattern = re.compile(r'^S\d{4}')
        server = sidekit.FeaturesServer(features_extractor=None,
                                        feature_filename_structure=path+"/{}.h5",
                                        sources=None,
                                        dataset_list=["energy","cep","vad"],
                                        mask="[0-19]",
                                        feat_norm="cmvn",
                                        global_cmvn=None,
                                        dct_pca=False,
                                        dct_pca_config=None,
                                        sdc=False,
                                        sdc_config=None,
                                        delta=True,
                                        double_delta=False,
                                        delta_filter=None,
                                        context=None,
                                        traps_dct_nb=None,
                                        rasta=True,
                                        keep_all_features=False)
        self.server = server
        self.maxlen = maxlen
        speakers_list = os.listdir(path)
        speakers_dir = []
        for i in range(len(speakers_list)):
            if re.match(pattern, speakers_list[i]):
                speakers_dir.append(path + '/' + speakers_list[i])
        speech = []
        num_speakers = 0
        real_speakers_list = []
        for i in speakers_dir:
            speech_list = os.listdir(i)
            if len(speech_list) > 20:
                for j in speech_list:
                    show = i.split('/')[-1] + '/' + j.split('.')[0]
                    speech.append(show)
                num_speakers += 1
                real_speakers_list.append(i.split('/')[-1])
        self.speech = np.asarray(speech)
        self.num_speakers = num_speakers
        self.speakers_list = np.asarray(real_speakers_list)
        a = [np.argwhere(self.speakers_list == i.split('/')[0])[0] for i in self.speech] # 对每个语音生成label
        self.train_labels = torch.tensor(a, dtype = torch.int64)
        self.train_labels.squeeze_()

    def get_num_class(self):
        return self.num_speakers
 
    def __len__(self):
        return len(self.speech)
    
    def __getitem__(self, i):
        show_list = self.speech[i]
        feature, _ = self.server.load(show_list, channel = 0)
        feature = feature.astype(np.float32)
        assert feature.shape[1] == 40, '{}'.format(feature.shape)
        feature = feature.reshape(1, -1, feature.shape[-1])
        feature = fixed_length(feature, self.maxlen)
        feature = torch.tensor(feature)
        label = self.train_labels[i]
        return feature, label

