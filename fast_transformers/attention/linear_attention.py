#
# Copyright (c) 2020 Idiap Research Institute, http://www.idiap.ch/
# Written by Angelos Katharopoulos <angelos.katharopoulos@idiap.ch>,
# Apoorv Vyas <avyas@idiap.ch>
#

"""Implement causally masked linear attention."""

from typing import Union

import torch
from torch.nn import Module

from fast_transformers.attention.causal_product import causal_dot_product


def elu_feature_map(x):
    return torch.nn.functional.elu(x) + 1


class LinearAttention(Module):
    def __init__(self, feature_map=elu_feature_map, eps=1e-6):
        super(LinearAttention, self).__init__()
        self.feature_map = feature_map
        self.eps = eps

    def forward(self, q, k, v, mask: Union[str, torch.Tensor] = "causal"):

        q = self.feature_map(q)
        k = self.feature_map(k)

        if mask == "causal":
            z = torch.einsum("nlhi,nlhi->nlh", q, k.cumsum(1)) + self.eps
            v = self.causal_linear(q, k, v)
            return v / z.unsqueeze(-1)
        else:
            k = k * mask.view(mask.size(0), mask.size(1), 1, 1)

            kv = torch.einsum("nshd,nshm->nhmd", k, v)
            z = torch.einsum("nlhd,nhd->nlh", q, k.sum(dim=1)) + self.eps
            return torch.einsum("nlhd,nhmd,nlh->nlhm", q, kv, 1 / z)

    def recurrent(self, q, k, v, memory=None):
        q = self.feature_map(q)
        k = self.feature_map(k)

        s_i, z_i = memory
        if z_i.requires_grad or s_i.requires_grad:
            z_i = z_i + k
            s_i = s_i + torch.einsum("nhd,nhm->nhdm", k, v)
        else:
            z_i += k
            s_i += torch.einsum("nhd,nhm->nhdm", k, v)

        z = torch.einsum("nhd,nhd->nh", q, z_i) + self.eps
        v = torch.einsum("nhd,nhdm,nh->nhm", q, s_i, 1 / z)

        return v, (s_i, z_i)

    @staticmethod
    def causal_linear(q, k, v):
        q = q.permute(0, 2, 1, 3).contiguous()
        k = k.permute(0, 2, 1, 3).contiguous()
        v = v.permute(0, 2, 1, 3).contiguous()
        V_new = causal_dot_product(q, k, v)
        return V_new.permute(0, 2, 1, 3).contiguous()


if __name__ == "__main__":
    torch.manual_seed(100)
    att = LinearAttention()
    x = torch.randn(1, 4, 2, 10)
    y = torch.randn(1, 4, 2, 10)
    z = torch.randn(1, 4, 2, 10)

    print(att(x, y, z, "causal").mean(-1))
    memory = None
    for i in range(4):
        res, memory = att.recurrent(x[:, i], y[:, i], z[:, i], memory)
        print(res.mean(-1))
