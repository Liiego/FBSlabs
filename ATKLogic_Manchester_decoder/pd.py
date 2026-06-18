## -*- coding: utf-8 -*-
## pd.py - 严格过滤空闲沿、支持ASCII/HEX/BIN/DEC多格式输出、零脏位残留的自适应曼彻斯特解码器

import sigrokdecode as srd

class SamplerateError(Exception):
    pass

class Ann:
    BIT, WORD, FRAME_ERROR = range(3)

class Bin:
    DATA = 0

class Decoder(srd.Decoder):
    api_version = 3
    id = 'manchester_saleae'
    name = 'Manchester_Saleae'
    longname = 'Manchester Self-Synchronizing Decoder'
    desc = 'Manchester decoder with auto-synchronization tracking and full format switching.'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['manchester_saleae']
    tags = ['Embedded/industrial']

    channels = (
        {'id': 'data', 'name': 'DATA', 'desc': 'Manchester data line'},
    )
    optional_channels = ()

    options = (
        {'id': 'bit_rate', 'desc': 'Baud rate (bps)', 'default': 9600},
        {'id': 'tolerance', 'desc': 'Timing Error Tolerance (%)', 'default': 25},
        {'id': 'data_format', 'desc': 'Data format', 'default': 'hex', 'values': ('hex', 'bin', 'ascii', 'dec')},
        {'id': 'bit_order', 'desc': 'Bit order', 'default': 'msb-first', 'values': ('msb-first', 'lsb-first')},
        {'id': 'word_size', 'desc': 'Word size (bits)', 'default': 8, 'values': (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)},
    )

    annotations = (
        ('bit', 'Bit'),
        ('word', 'Word'),
        ('frame_error', 'Frame Error'),
    )
    annotation_rows = (
        ('data_bits', 'Decoded Bits', (Ann.BIT,)),
        ('data_words', 'Decoded Words', (Ann.WORD,)),
        ('errors', 'Errors', (Ann.FRAME_ERROR,)),
    )
    binary = (
        ('manchester-data', 'Manchester data dump'),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None
        self.mT = 0
        self.mTError = 0
        self.state = 'FIND_LONG_IDLE'
        self.next_expected_middle = 0
        self.bit_start_sample = 0
        
        # 🚀 事务打包缓冲区：凑不满指定字长（word_size）时，不污染屏幕绘制
        self.bits_accum = []       # 缓存二进制0/1的箱子
        self.bits_positions = []   # 暂存每个比特在时间轴上的 (start, end) 物理坐标
        self.word_start_sample = 0

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.out_binary = self.register(srd.OUTPUT_BINARY)

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value
            total_bit_width_samples = float(self.samplerate) / self.options['bit_rate']
            self.mT = int(total_bit_width_samples / 2.0)
            self.mTError = int(self.mT * (self.options['tolerance'] / 100.0))

    def handle_bit_output(self, center_edge_sample, val):
        """ 🎯 增强的事务缓冲级比特处理：拼满 word_size 才会将 bits 和高级字一同引爆输出 """
        box_start = center_edge_sample - self.mT
        box_end = center_edge_sample + self.mT
        if box_start < 0: box_start = 0
        
        # 将本次解出的单个位信息先隔离在内存队列里
        self.bits_accum.append(val)
        self.bits_positions.append((box_start, box_end))
        
        if len(self.bits_accum) == 1:
            self.word_start_sample = box_start
            
        target_word_size = self.options['word_size']
        
        # 🚀 只有当缓冲器中的位凑满了用户配置的字长时（例如 8 bit），才进行集体大渲染
        if len(self.bits_accum) == target_word_size:
            
            # 1. 批量绘制第一层的 Bits 气泡（去除任何孤立残留的可能性）
            for i in range(target_word_size):
                b_start, b_end = self.bits_positions[i]
                b_val = self.bits_accum[i]
                self.put(b_start, b_end, self.out_ann, [Ann.BIT, [str(b_val)]])
                
            # 2. 依据大小端规则（Bit Order）拼装底层的数值值
            final_val = 0
            if self.options['bit_order'] == 'msb-first':
                for bit in self.bits_accum:
                    final_val = (final_val << 1) | bit
            else:
                for i, bit in enumerate(self.bits_accum):
                    final_val |= (bit << i)
                    
            # 3. 🚀 核心增加：多数据格式（HEX/BIN/ASCII/DEC）自适应转换引擎
            fmt = self.options['data_format']
            if fmt == 'hex':
                # 十六进制格式 (例如 8位下为 "5A", 16位下自动变为 "0xBADE" 的对齐格式)
                fmt_len = (target_word_size + 3) // 4
                word_str = ("0x%%0%dX" % fmt_len) % final_val
            elif fmt == 'bin':
                # 二进制格式 (例如 "0b01011010")
                word_str = "0b" + "".join(str(b) for b in self.bits_accum)
            elif fmt == 'dec':
                # 十进制十数值数字
                word_str = str(final_val)
            elif fmt == 'ascii':
                # 🎯 ASCII 码转换逻辑
                if 32 <= final_val <= 126:
                    # 可视化标准 ASCII 字符 (如 'A', 'h')
                    word_str = "'%s'" % chr(final_val)
                else:
                    # 不可见控制字符转为点或转义提示
                    word_str = "[.%02X]" % final_val
            else:
                word_str = str(final_val)

            # 4. 完美渲染第二层的高级数据字（Word 行）
            self.put(self.word_start_sample, box_end, self.out_ann, [Ann.WORD, [word_str]])
            
            # 5. 清空当前批次，准备迎接下一组
            self.bits_accum = []
            self.bits_positions = []

    def reset_buffers(self):
        """ 清空还没拼完 8 位的箱子，直接从内存层面强行撤回，使其不在屏幕上留下痕迹 """
        self.bits_accum = []
        self.bits_positions = []

    def decode(self):
        self.state = 'FIND_LONG_IDLE'
        self.reset_buffers()
        old_sample = 0

        while True:
            # 挂起阻断，等待物理边缘触发
            pin_state = self.wait({0: 'e'})
            current_sample = self.samplenum
            current_pin = pin_state[0]

            # 计算本次翻转和上一个物理沿之间的跨度距离
            edge_distance = current_sample - old_sample

            # 🚀 全局监控：如果两沿距离极大，意味着进入长空闲（帧间断开点）
            if old_sample > 0 and edge_distance > ((2 * self.mT) + (self.mTError * 2)):
                # 如果还有没凑满字长的零碎孤立位，无情抹除清除
                self.reset_buffers()
                self.state = 'FIND_LONG_IDLE'

            # =================================================================
            # 状态 1：长空闲捕获态
            # =================================================================
            if self.state == 'FIND_LONG_IDLE':
                if old_sample == 0 or edge_distance > ((2 * self.mT) + (self.mTError * 2)):
                    self.state = 'DECODING'
                    
                    # 琻捷及标准 TPMS 首跳变数据沿固定逻辑值翻译为 0
                    raw_bit = 0
                    self.handle_bit_output(current_sample, raw_bit)
                    
                    # 对齐未来的名义理论步进轴线
                    self.next_expected_middle = current_sample + (2 * self.mT)
                    self.bit_start_sample = current_sample
                
                old_sample = current_sample
                continue

            # =================================================================
            # 状态 2：连续节拍追踪状态
            # =================================================================
            elif self.state == 'DECODING':
                # 极性硬翻译：下降沿=1，上升沿=0
                raw_bit = 1 if current_pin == 0 else 0

                is_short = (self.mT - self.mTError) < edge_distance < (self.mT + self.mTError)
                is_long  = ((2 * self.mT) - self.mTError) < edge_distance < ((2 * self.mT) + self.mTError)

                time_drift = abs(current_sample - self.next_expected_middle)

                if is_short:
                    if time_drift < (self.mTError * 2):
                        self.handle_bit_output(current_sample, raw_bit)
                        self.next_expected_middle = current_sample + (2 * self.mT)
                        self.bit_start_sample = current_sample
                    else:
                        pass # 过滤位边界衔接沿
                        
                elif is_long:
                    if time_drift < (self.mTError * 2):
                        self.handle_bit_output(current_sample, raw_bit)
                        self.next_expected_middle = current_sample + (2 * self.mT)
                        self.bit_start_sample = current_sample
                    else:
                        # 尾部突变长电平，未对齐轨道，踢回等长空闲，抹除未完工脏数据
                        self.reset_buffers()
                        self.state = 'FIND_LONG_IDLE'
                    
                else:
                    # 波形受到空中严重杂散干扰出现畸变，重置
                    self.reset_buffers()
                    self.state = 'FIND_LONG_IDLE'

                old_sample = current_sample