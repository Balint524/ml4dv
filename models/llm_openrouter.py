import random
import time

from models.llm_base import *
import os
import json
import requests

import tiktoken
from models.llm_gpt import num_tokens_from_messages

class OpenRouter(BaseLLM):
    def __init__(
        self,
        system_prompt: str = "",
        model_name="meta-llama/llama-3-70b-instruct",
        temperature=0.4,
        top_p=1,
        max_gen_tokens=600,
        best_iter_buffer_resetting: str = "STABLE",
        compress_msg_algo: str = "best 3",
        prioritise_harder_bins: bool = False,  # not needed if compress_msg_algo as "Successful Difficult Responses"
    ):
        prioritise_harder_bins = (
            prioritise_harder_bins
            or compress_msg_algo == "Successful Difficult Responses"
        )
        super().__init__(
            system_prompt, best_iter_buffer_resetting, prioritise_harder_bins,
        )
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        assert openrouter_api_key is not None, "OpenRouter API key not found."
        self.api_key = openrouter_api_key

        self.model_max_context = 4096
        self.temperature = temperature
        self.top_p = top_p
        self.max_gen_tokens = max_gen_tokens
        self.model_name = model_name

        self.messages = []
        self.recent_msgs = []
        if self.system_prompt != "":
            self.messages.append({"role": "system", "content": self.system_prompt})

        self.compress_msg_algo: Callable[
            [], List[Dict[str, str]]
        ] = self.__resolve_msg_compress_algo(compress_msg_algo)

    def __resolve_msg_compress_algo(self, compress_msg_algo) -> Callable:
        if compress_msg_algo in [
            "best 3",
            "Successful Responses",
            "Successful Difficult Responses",
        ]:
            return self.__best_3
        elif compress_msg_algo in [
            "best 2 recent 1",
            "Mixed Recent and Successful Responses",
        ]:
            return self.__best_2_recent_1
        elif compress_msg_algo in ["recent 3", "Recent Responses"]:
            return self.__recent_3
        else:
            methods = [
                "recent 3",
                "best 3",
                "best 2 recent 1",
                "Recent Responses",
                "Mixed Recent and Successful Responses",
                "Successful Responses",
                "Successful Difficult Responses",
            ]
            raise ValueError(
                f"Invalid conversation compression algorithm {compress_msg_algo}. \\"
                f"Please use one of the following methods: {methods}"
            )

    def __str__(self):
        return self.model_name

    def __call__(self, prompt: str) -> Tuple[str, Tuple[int, int, int]]:
        print("Calling")
        self._compress_conversation()
        self.messages.append({"role": "user", "content": prompt})
        self.recent_msgs.append({"role": "user", "content": prompt})

        token_cnt = self._check_token_num()
        if (
            self.model_max_context is None
            or token_cnt + self.max_gen_tokens <= self.model_max_context
        ):
            model = self.model_name
        else:
            model = self.model_name

        for delay in [2**x for x in range(0, 6)]:
            try:
                response = requests.post(
                timeout=30,
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}"
                },
                data=json.dumps({
                    "model": model, # Optional
                    "messages": self.messages,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_tokens": self.max_gen_tokens,
                })
                )
                result = response.json()
            except Exception as e:
                randomness_collision_avoidance = random.randint(0, 1000) / 300.0
                sleep_dur = delay + randomness_collision_avoidance
                print(f"Error: {e}. Retrying in {round(sleep_dur, 2)} seconds.")
                time.sleep(sleep_dur)
                continue
            else:
                response_choices: List[Dict[str, str]] = [
                    choice["message"] for choice in result["choices"]
                ]
                self.messages.append(response_choices[0])
                self.recent_msgs.append(response_choices[0])
                self.total_msg_cnt += 1
                input_token = result["usage"]["prompt_tokens"]
                output_token = result["usage"]["completion_tokens"]
                total_token = input_token + output_token
                print("Returned")
                return response_choices[0]["content"], (
                    input_token,
                    output_token,
                    total_token,
                )

    def _compress_conversation(self):
        # STABLE RST & CLEAR RST
        if (
            self.best_iter_buffer_resetting in ["STABLE", "CLEAR"]
            and len(self.messages) < 4 + 2 * OpenRouter.REMAIN_ITER_NUM
        ):
            return
        if self.messages[0]["role"] == "system":
            init = self.messages[:3]
        else:
            init = self.messages[:2]

        # Keep recent / previous successful iter messages
        self.messages = init + self.compress_msg_algo()
        return

    def __best_3(self) -> List[Dict[str, str]]:
        return self._select_successful(n_best=3)

    def __best_2_recent_1(self) -> List[Dict[str, str]]:
        best = self._select_successful(n_best=2)
        recent = self.recent_msgs[-2:]
        return best + recent

    def __recent_3(self) -> List[Dict[str, str]]:
        return self.messages[-2 * 3 :]

    def _check_token_num(self) -> int:
        return num_tokens_from_messages(self.messages, self.model_name)

    def reset(self):
        self.messages.clear()
        self.recent_msgs.clear()
        if self.system_prompt != "":
            self.messages.append({"role": "system", "content": self.system_prompt})
        # CLEAR RST
        if self.best_iter_buffer_resetting == "CLEAR":
            self.best_messages.clear()