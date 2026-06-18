##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2024 ATK-Logic Manchester Decoder
##


'''
Manchester encoding protocol decoder.

Manchester (also known as Biphase-L) is a self-clocking binary encoding scheme where each bit period is divided into two halves. A transition always occurs in the middle of each bit period for clock synchronization.

Supported encoding variants:
  - Standard (G.E. Thomas): low-to-high transition = logic 0,
    high-to-low transition = logic 1.
  
'''

from .pd import Decoder
