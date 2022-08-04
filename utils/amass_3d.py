from torch.utils.data import Dataset,DataLoader
import numpy as np
#from h5py import File
#import scipy.io as sio
from matplotlib import pyplot as plt
import torch
import os
from utils.ang2joint import *
import networkx as nx

'''
adapted from
https://github.com/wei-mao-2019/HisRepItself/blob/master/utils/amass3d.py
'''


class Datasets(Dataset):
    def __init__(self, data_dir, input_n, output_n, skip_rate, actions=None, split=0):
        """
        :param path_to_data:
        :param actions:
        :param input_n:
        :param output_n:
        :param dct_used:
        :param split: 0 train, 1 testing, 2 validation
        :param sample_rate:
        """
        self.path_to_data = os.path.join(data_dir,'AMASS')         #  "D:\data\AMASS\\"
        self.split = split
        self.in_n = input_n
        self.out_n = output_n
        # self.sample_rate = opt.sample_rate
        self.p3d = []
        self.keys = []
        self.data_idx = []
        self.joint_used = np.arange(4, 22) # start from 4 for 17 joints, removing the non moving ones
        seq_len = self.in_n + self.out_n

        amass_splits = ['training_fnames.txt',
                        'validation_fnames.txt',
                        'test_fnames.txt']

        # from human_body_prior.body_model.body_model import BodyModel
        # from smplx import lbs
        # root_path = os.path.dirname(__file__)
        # bm_path = root_path[:-6] + '/body_models/smplh/neutral/model.npz'
        # bm = BodyModel(bm_path=bm_path, num_betas=16, batch_size=1, model_type='smplh')
        # beta_mean = np.array([0.41771687, 0.25984767, 0.20500051, 0.13503872, 0.25965645, -2.10198147, -0.11915666,
        #                       -0.5498772, 0.30885323, 1.4813145, -0.60987528, 1.42565269, 2.45862726, 0.23001716,
        #                       -0.64180912, 0.30231911])
        # beta_mean = torch.from_numpy(beta_mean).unsqueeze(0).float()
        # # Add shape contribution
        # v_shaped = bm.v_template + lbs.blend_shapes(beta_mean, bm.shapedirs)
        # # Get the joints
        # # NxJx3 array
        # p3d0 = lbs.vertices2joints(bm.J_regressor, v_shaped)  # [1,52,3]
        # p3d0 = (p3d0 - p3d0[:, 0:1, :]).float().cuda().cpu().data.numpy()
        # parents = bm.kintree_table.data.numpy()[0, :]
        # np.savez_compressed('smpl_skeleton.npz', p3d0=p3d0, parents=parents)

        # load mean skeleton
        skel = np.load('./body_models/smpl_skeleton.npz')
        p3d0 = torch.from_numpy(skel['p3d0']).float().cuda()
        parents = skel['parents']
        parent = {}
        for i in range(len(parents)):
            parent[i] = parents[i]
        n = 0
        
        file_list_name = amass_splits[split]
        with open(file_list_name) as file:
            lines = file.readlines()
            lines = [line.rstrip() for line in lines]
        
        for line in lines:
            act_path = os.path.join(self.path_to_data, line)
            pose_all = np.load(act_path)
            try:
                poses = pose_all['poses']
            except:
                print('no poses at {}'.format(act_path))
                continue
            try:
                frame_rate = pose_all['mocap_framerate']
            except:
                print('no mocap_framerate at {}. substitute with 60'.format(act_path))
                frame_rate = 60
            # gender = pose_all['gender']
            # dmpls = pose_all['dmpls']
            # betas = pose_all['betas']
            # trans = pose_all['trans']

            # poses (frames, 156)
            # Some are more than 156...
            fn = poses.shape[0]
            sample_rate = int(frame_rate // 25)
            fidxs = range(0, fn, sample_rate)
            fn = len(fidxs)
            poses = poses[fidxs]
            poses = torch.from_numpy(poses).float().cuda()
            poses = poses.reshape([fn, -1, 3])
            # remove global rotation
            poses[:, 0] = 0
            p3d0_tmp = p3d0.repeat([fn, 1, 1])
            p3d = ang2joint(p3d0_tmp, poses, parent)
            # self.p3d[(ds, sub, act)] = p3d.cpu().data.numpy()
            self.p3d.append(p3d)

            if split == 2:
                valid_frames = np.arange(0, fn - seq_len + 1, skip_rate)
            else:
                valid_frames = np.arange(0, fn - seq_len + 1, skip_rate)

            # tmp_data_idx_1 = [(ds, sub, act)] * len(valid_frames)
            self.keys.append((act_path))
            tmp_data_idx_1 = [n] * len(valid_frames)
            tmp_data_idx_2 = list(valid_frames)
            self.data_idx.extend(zip(tmp_data_idx_1, tmp_data_idx_2))
            n += 1

    def __len__(self):
        return np.shape(self.data_idx)[0]

    def __getitem__(self, item):
        key, start_frame = self.data_idx[item]
        fs = np.arange(start_frame, start_frame + self.in_n + self.out_n)
        return self.p3d[key][fs]  # , key


# In[12]:


def normalize_A(A): # given an adj.matrix, normalize it by multiplying left and right with the degree matrix, in the -1/2 power
        
        A=A+np.eye(A.shape[0])
        
        D=np.sum(A,axis=0)
        
        
        D=np.diag(D.A1)

        
        D_inv = D**-0.5
        D_inv[D_inv==np.infty]=0
        
        return D_inv*A*D_inv


# In[ ]:


def spatio_temporal_graph(joints_to_consider,temporal_kernel_size,spatial_adjacency_matrix): # given a normalized spatial adj.matrix,creates a spatio-temporal adj.matrix

    
    number_of_joints=joints_to_consider

    spatio_temporal_adj=np.zeros((temporal_kernel_size,number_of_joints,number_of_joints))
    for t in range(temporal_kernel_size):
        for i in range(number_of_joints):
            spatio_temporal_adj[t,i,i]=1 # create edge between same body joint,for t consecutive frames
            for j in range(number_of_joints):
                if spatial_adjacency_matrix[i,j]!=0: # if the body joints are connected
                    spatio_temporal_adj[t,i,j]=spatial_adjacency_matrix[i,j]
    return spatio_temporal_adj


# In[20]:


def get_adj_AMASS(joints_to_consider,temporal_kernel_size): # returns adj.matrix to be fed to the network
    if joints_to_consider==22:
        edgelist = [
                    (0, 1), (0, 2), #(0, 3),
                    (1, 4), (5, 2), #(3, 6),
                    (7, 4), (8, 5), #(6, 9),
                    (7, 10), (8, 11), #(9, 12),
                    #(12, 13), (12, 14),
                    (12, 15),
                    #(13, 16), (12, 16), (14, 17), (12, 17),
                    (12, 16), (12, 17),
                    (16, 18), (19, 17), (20, 18), (21, 19),
                    #(22, 20), #(23, 21),#wrists
                    (1, 16), (2, 17)]

    # create a graph
    G=nx.Graph()
    G.add_edges_from(edgelist)
    # create adjacency matrix
    A = nx.adjacency_matrix(G,nodelist=list(range(0,joints_to_consider))).todense()
    #normalize adjacency matrix
    A=normalize_A(A)
    return torch.Tensor(spatio_temporal_graph(joints_to_consider,temporal_kernel_size,A))


# In[23]:


def mpjpe_error(batch_pred,batch_gt):
    #assert batch_pred.requires_grad==True
    #assert batch_gt.requires_grad==False

    
    batch_pred=batch_pred.contiguous().view(-1,3)
    batch_gt=batch_gt.contiguous().view(-1,3)

    return torch.mean(torch.norm(batch_gt-batch_pred,2,1))


# In[ ]:




