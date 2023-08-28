#!/bin/env python3

from datetime import datetime
import zmq
import pickle
from contextlib import closing
import sys
import os

directory = os.path.dirname(os.path.abspath("__file__"))
sys.path.insert(0, os.path.dirname(directory))
# print(sys.path)

from ibex_decoder.shared_types import *
from global_shared_types import *
from agents.agent_random import RandomAgent
from agents.agents_CLI import *
from agents.agent_LLM import *
from prompt_generators.prompt_generator_fixed_ID import FixedPromptGenerator4ID1
from prompt_generators.prompt_generator_template_ID import *
# from models.llm_llama2 import Llama2
from models.llm_gpt import ChatGPT
from stimuli_extractor import DumbExtractor
from stimuli_filter import Filter
from loggers.logger_csv import CSVLogger
from loggers.logger_txt import TXTLogger
from agents.agent_ID_dumb import DumbAgent4ID


class StimulusSender:
    def __init__(self, zmq_addr):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(zmq_addr)

    def send_stimulus(self, stimulus_obj):
        self.socket.send_pyobj(stimulus_obj)
        coverage_obj = self.socket.recv_pyobj()

        if not isinstance(coverage_obj, CoverageDatabase):
            raise RuntimeError("Bad format of coverage response")

        return coverage_obj

    def close(self):
        if self.socket:
            self.socket.close()


def main():
    server_ip_port = input(
        "Please enter server's IP and port (e.g. 127.0.0.1:5050, 128.232.65.218:5555): "
    )

    # build components
    prompt_generator = TemplatePromptGenerator4ID2(
        bin_descr_path="../examples_ID/bins_description.txt",
        sampling_missed_bins_method="IDNEWEST",
    )

    # stimulus_generator = Llama2(system_prompt=prompt_generator.generate_system_prompt())
    # print('Llama2 successfully built')
    stimulus_generator = ChatGPT(
        system_prompt=prompt_generator.generate_system_prompt(),
        compress_msg_algo="best 3",
    )
    extractor = DumbExtractor()
    stimulus_filter = Filter(0x0, 0xFFFFFFFF)

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
        dialog_bound=1000,
        rst_plan=rst_plan_IDADAR,
    )
    print("Agent successfully built\n")

    # agent = RandomAgent(3000000)

    # run test
    g_dut_state = GlobalDUTState()
    g_coverage = GlobalCoverageDatabase()

    with closing(StimulusSender(f"tcp://{server_ip_port}")) as stimulus_sender:
        while not agent.end_simulation(g_dut_state, g_coverage):
            stimulus = agent.generate_next_value(g_dut_state, g_coverage)
            coverage = stimulus_sender.send_stimulus(stimulus)
            g_coverage.set(coverage)

        coverage = stimulus_sender.send_stimulus(None)
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
        # print(
        #     f"Finished at dialog #{agent.dialog_index}, message #{agent.msg_index}, \n"
        #     f"with total {agent.total_msg_cnt} messages \n"
        #     f"Hits: {coverage_plan}, \n"
        #     f"Coverage rate: {g_coverage.get_coverage_rate()}\n"
        # )


if __name__ == "__main__":
    main()
