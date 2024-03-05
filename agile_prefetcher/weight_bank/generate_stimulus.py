#!/bin/env python3
import csv
import time
from datetime import datetime
import zmq
import pickle
from contextlib import closing
import sys
import os
import numpy as np

directory = os.path.dirname(os.path.abspath("__file__"))
sys.path.insert(0, os.path.dirname("/".join(directory.split("/")[:-1])))

from agile_prefetcher.weight_bank.shared_types import *
from global_shared_types import *
from agents.agent_random import *
from agents.agent_LLM import *
from prompt_generators.prompt_generator_template_AG_WB import *
from models.llm_gpt import ChatGPT
from stimuli_extractor import UniversalExtractor
from stimuli_filter import UniversalFilter
from loggers.logger_csv import CSVLogger
from loggers.logger_txt import TXTLogger

class StimulusSender:
    def __init__(self, zmq_addr):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(zmq_addr)

    def send_stimulus(self, stimulus_obj):
        self.socket.send_pyobj(stimulus_obj)
        state_coverage_obj = self.socket.recv_pyobj()

        if not isinstance(state_coverage_obj, tuple):
            raise RuntimeError("Bad format of coverage response")
        if not isinstance(state_coverage_obj[0], DUTState):
            raise RuntimeError("Bad format of coverage response element 0")
        if not isinstance(state_coverage_obj[1], CoverageDatabase):
            raise RuntimeError("Bad format of coverage response element 1")

        return state_coverage_obj

    def close(self):
        if self.socket:
            self.socket.close()

def random_experiment():
    print("Running random experiment on AG_WB...\n")

    server_ip_port = input(
        "Please enter server's IP and port (e.g. 127.0.0.1:5050, 128.232.65.218:5555): "
    )

    CYCLES = 16
    agent = RandomAgent4AG_WB(total_cycle=CYCLES, seed=int(datetime.now().timestamp()))

    # run test
    stimulus = Stimulus(value=0, finish=False)
    g_dut_state = GlobalDUTState()
    g_coverage = GlobalCoverageDatabase()

    with closing(StimulusSender(f"tcp://{server_ip_port}")) as stimulus_sender:
        while not agent.end_simulation(g_dut_state, g_coverage):
            stimulus.value = agent.generate_next_value(g_dut_state, g_coverage)
            print(stimulus.value)
            dut_state, coverage = stimulus_sender.send_stimulus(stimulus)
            g_dut_state.set(dut_state)
            g_coverage.set(coverage)

        coverage_plan = {
            k: v for (k, v) in g_coverage.get_coverage_plan().items() if v > 0
        }
        print(
            f"Finished random agent on AGILE weight bank with {CYCLES} cycles \n"
            f"Hits: {coverage_plan}, \n"
            f"Coverage rate: {g_coverage.get_coverage_rate()}\n"
        )

        stimulus.value = None
        stimulus.finish = True
        stimulus_sender.send_stimulus(stimulus)

def main():
    print("Running main experiment on AG_WB...")

    server_ip_port = input(
        "Please enter server's IP and port (e.g. 127.0.0.1:5050, 128.232.65.218:5555): "
    )

    # build components
    prompt_generator = TemplatePromptGeneratorAG_WB(
        bin_descr_path="../../examples_AG_WB/bins_description.txt",
        dut_code_path="prefetcher_weight_bank.sv",
        tb_code_path="agile_prefetcher_weight_bank_cocotb.py",
        sampling_missed_bins_method="RANDOM",
        code_summary_type=1
    )

    # stimulus_generator = Llama2(system_prompt=prompt_generator.generate_system_prompt())
    # print('Llama2 successfully built')
    stimulus_generator = ChatGPT(
        system_prompt=prompt_generator.generate_system_prompt(),
        best_iter_buffer_resetting="STABLE",
        compress_msg_algo="best 3",
        prioritise_harder_bins=False,
    )
    extractor = UniversalExtractor(2)
    stimulus_filter = UniversalFilter([[1,64],[1,64]])

    # build loggers
    prefix = "./logs/"
    t = datetime.now()
    t = t.strftime("%Y%m%d_%H%M%S")
    logger_txt = TXTLogger(f"{prefix}{t}.txt")
    logger_csv = CSVLogger(f"{prefix}{t}.csv")

    # create agent
    agent = LLMAgent(
        prompt_generator,
        stimulus_generator,
        extractor,
        stimulus_filter,
        [logger_txt, logger_csv],
        dialog_bound=300,
        rst_plan=rst_plan_Normal_Tolerance,
    )
    print("Agent successfully built\n")

    # run test
    g_dut_state = GlobalDUTState()
    g_coverage = GlobalCoverageDatabase()
    stimulus = Stimulus(value=0, finish=False)

    with closing(StimulusSender(f"tcp://{server_ip_port}")) as stimulus_sender:
        while not agent.end_simulation(g_dut_state, g_coverage):
            stimulus.value = agent.generate_next_value(g_dut_state, g_coverage)
            if(isinstance(stimulus.value, int)):
                stimulus.value = [1,1]
            print(stimulus)
            dut_state, coverage = stimulus_sender.send_stimulus(stimulus)
            g_dut_state.set(dut_state)
            g_coverage.set(coverage)

        dut_state, coverage = stimulus_sender.send_stimulus(Stimulus(value=[1,1], finish=True))
        # coverage.output_coverage()

        g_coverage.set(coverage)
        # print(f"Full coverage plan: {g_coverage.get_coverage_plan()}\n")
        coverage_plan = {
            k: v for (k, v) in g_coverage.get_coverage_plan().items() if v > 0
        }
        print(
            f"Finished with hits: {coverage_plan}\n"
            f"Coverage: {g_coverage.get_coverage_rate()}\n"
        )


if __name__ == "__main__":
    main()