"""Attempt to implement MRKL systems as described in arxiv.org/pdf/2205.00445.pdf."""
from typing import Any, Callable, List, NamedTuple, Optional, Tuple

from langchain.chains.llm import LLMChain
from langchain.llms.base import LLM
from langchain.prompts import PromptTemplate
from langchain.routing_chains.mrkl.prompt import BASE_TEMPLATE
from langchain.routing_chains.router import LLMRouter
from langchain.routing_chains.routing_chain import RoutingChain
from langchain.routing_chains.tools import Tool

FINAL_ANSWER_ACTION = "Final Answer: "


class ChainConfig(NamedTuple):
    """Configuration for chain to use in MRKL system.

    Args:
        action_name: Name of the action.
        action: Action function to call.
        action_description: Description of the action.
    """

    action_name: str
    action: Callable
    action_description: str


def get_action_and_input(llm_output: str) -> Tuple[str, str]:
    """Parse out the action and input from the LLM output."""
    ps = [p for p in llm_output.split("\n") if p]
    if ps[-1].startswith("Final Answer"):
        directive = ps[-1][len(FINAL_ANSWER_ACTION) :]
        return "Final Answer", directive
    if not ps[-1].startswith("Action Input: "):
        raise ValueError(
            "The last line does not have an action input, "
            "something has gone terribly wrong."
        )
    if not ps[-2].startswith("Action: "):
        raise ValueError(
            "The second to last line does not have an action, "
            "something has gone terribly wrong."
        )
    action = ps[-2][len("Action: ") :]
    action_input = ps[-1][len("Action Input: ") :]
    return action, action_input.strip(" ").strip('"')


class ZeroShotRouter(LLMRouter):
    """Router for the MRKL chain."""

    @property
    def observation_prefix(self) -> str:
        """Prefix to append the observation with."""
        return "Observation: "

    @property
    def router_prefix(self) -> str:
        """Prefix to append the router call with."""
        return "Thought:"

    @classmethod
    def from_llm_and_tools(cls, llm: LLM, tools: List[Tool]) -> "ZeroShotRouter":
        """Construct a router from an LLM and tools."""
        tool_strings = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
        tool_names = ", ".join([tool.name for tool in tools])
        template = BASE_TEMPLATE.format(tools=tool_strings, tool_names=tool_names)
        prompt = PromptTemplate(template=template, input_variables=["input"])
        llm_chain = LLMChain(llm=llm, prompt=prompt)
        return cls(llm_chain=llm_chain)

    def _extract_tool_and_input(self, text: str) -> Optional[Tuple[str, str]]:
        return get_action_and_input(text)


class MRKLChain(RoutingChain):
    """Chain that implements the MRKL system.

    Example:
        .. code-block:: python

            from langchain import OpenAI, MRKLChain
            from langchain.chains.mrkl.base import ChainConfig
            llm = OpenAI(temperature=0)
            prompt = PromptTemplate(...)
            chains = [...]
            mrkl = MRKLChain.from_chains(llm=llm, prompt=prompt)
    """

    @classmethod
    def from_chains(
        cls, llm: LLM, chains: List[ChainConfig], **kwargs: Any
    ) -> "MRKLChain":
        """User friendly way to initialize the MRKL chain.

        This is intended to be an easy way to get up and running with the
        MRKL chain.

        Args:
            llm: The LLM to use as the router LLM.
            chains: The chains the MRKL system has access to.
            **kwargs: parameters to be passed to initialization.

        Returns:
            An initialized MRKL chain.

        Example:
            .. code-block:: python

                from langchain import LLMMathChain, OpenAI, SerpAPIChain, MRKLChain
                from langchain.chains.mrkl.base import ChainConfig
                llm = OpenAI(temperature=0)
                search = SerpAPIChain()
                llm_math_chain = LLMMathChain(llm=llm)
                chains = [
                    ChainConfig(
                        action_name = "Search",
                        action=search.search,
                        action_description="useful for searching"
                    ),
                    ChainConfig(
                        action_name="Calculator",
                        action=llm_math_chain.run,
                        action_description="useful for doing math"
                    )
                ]
                mrkl = MRKLChain.from_chains(llm, chains)
        """
        tools = [
            Tool(name=c.action_name, func=c.action, description=c.action_description)
            for c in chains
        ]
        return cls.from_tools_and_llm(tools, llm, **kwargs)

    @classmethod
    def from_tools_and_llm(
        cls, tools: List[Tool], llm: LLM, **kwargs: Any
    ) -> "MRKLChain":
        """User friendly way to initialize the MRKL chain.

        This is intended to be an easy way to get up and running with the
        MRKL chain.

        Args:
            tools: The tools the MRKL system has access to.
            llm: The LLM to use as the router LLM.
            **kwargs: parameters to be passed to initialization.

        Returns:
            An initialized MRKL chain.

        Example:
            .. code-block:: python

                from langchain import LLMMathChain, OpenAI, SerpAPIChain, MRKLChain
                from langchain.routing_chains.tools import ToolConfig
                llm = OpenAI(temperature=0)
                search = SerpAPIChain()
                llm_math_chain = LLMMathChain(llm=llm)
                tools = [
                    ToolConfig(
                        tool_name = "Search",
                        tool=search.search,
                        tool_description="useful for searching"
                    ),
                    ToolConfig(
                        tool_name="Calculator",
                        tool=llm_math_chain.run,
                        tool_description="useful for doing math"
                    )
                ]
                mrkl = MRKLChain.from_tools_and_llm(llm, tools)
        """
        router = ZeroShotRouter.from_llm_and_tools(llm, tools)
        return cls(router=router, tools=tools, **kwargs)