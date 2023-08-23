from agents.agent_base import *
import random


class RandomAgent(BaseAgent):
    def __init__(self, total_cycle=1000000):
        super().__init__()
        self.seed = 0
        random.seed(self.seed)
        self.total_cycle = total_cycle
        self.current_cycle = 0

    def end_simulation(
        self, dut_state: GlobalDUTState, coverage_database: GlobalCoverageDatabase
    ):
        return not self.current_cycle < self.total_cycle

    def reset(self):
        self.current_cycle = 0

    def generate_next_value(
        self, dut_state: GlobalDUTState, coverage_database: GlobalCoverageDatabase
    ):
        if self.current_cycle % 10000 == 0:
            print(f"Generating {self.current_cycle + 1} stimulus\n")
        self.current_cycle += 1
        return random.getrandbits(32)
