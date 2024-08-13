import json
from typing import Dict, Any, Generator
from core.utils.code_tools import code_tools
from core.interpreter.ast_code_runner import ASTCodeRunner
import re
from .plan_template_manager import PlanTemplateManager
from .logger import logger

class StockQueryStream:
    def __init__(self, llm_client, stock_data_provider):
        self.llm_client = llm_client
        self.stock_data_provider = stock_data_provider
        self.code_runner = ASTCodeRunner()
        self.template_manager = PlanTemplateManager(llm_client)
        self.template_manager.load_templates_from_file("./json/stock_flows.md")
        code_tools.add_var('stock_data_provider', self.stock_data_provider)
        code_tools.add_var('llm_client', self.llm_client) 

    def query(self, query: str) -> Generator[Dict[str, Any], None, None]:
        logger.info(f"开始处理查询: {query}")
        yield {"type": "message", "content": "开始生成执行计划..."}
        plan = yield from self._generate_plan(query)
        yield {"type": "message", "content": "执行计划生成完成，开始执行..."}
        yield from self._execute_plan(plan, query)
        logger.info("查询处理完成")

    def _generate_plan(self, query: str) -> Generator[Dict[str, Any], None, None]:
        logger.info("正在生成执行计划...")
        provider_description = self.stock_data_provider.get_self_description()
        best_template = self.template_manager.get_best_template(query)
        
        prompt = f"""
        根据以下查询要求生成一个单步骤的执行计划：
        {query}

        可用的数据提供函数如下：
        {provider_description}

        基于以下模板生成计划：
        {best_template['template']}

        请生成一个单步骤的执行计划。计划应该是一个 JSON 格式的对象，包含以下字段：
        1. "description": 需要完成的任务描述
        2. "pseudocode": 完成任务的伪代码
        3. "tip_help": 这个步骤的注意事项
        4. "functions": 需要使用的数据提供函数列表,只列"可用的数据提供函数"提及的函数

        请确保在生成计划时包含详细的提示词构建指南和输出格式要求。
        注意：在伪代码的最后，请使用 code_tools.add("output_result", final_result) 来存储最终结果。

        对于涉及 LLM 分析的，请在伪代码中详细说明：
        1. 构建详细的提示词，包含所有必要的数据和上下文信息。
        2. 提示词中明确指定 LLM 输出应为 JSON 格式。
        3. 提示词中包含了"模板"中所要求的内容。
        4. 使用 llm_client.one_chat(prompt) 来调用 LLM 进行分析

        请返回一个格式化的 JSON 计划，并用 ```json ``` 包裹。
        """
        plan_response = ""
        for chunk in self.llm_client.one_chat(prompt, is_stream=True):
            plan_response += chunk
            yield {"type": "message", "content": chunk}

        plan = self._parse_plan(plan_response)
        logger.info("执行计划生成完成")
        yield {"type": "message", "content": "data: [Done]", "plan": plan}
        return plan

    def _parse_plan(self, plan_response: str) -> dict:
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, plan_response, re.DOTALL)
        if matches:
            return json.loads(matches[0])
        else:
            raise ValueError("无法解析计划 JSON")

    def _get_functions_docs(self, function_names: list) -> str:
        docs = []
        for func_name in function_names:
            doc = self.stock_data_provider.get_function_docstring(func_name)
            docs.append(f"{func_name}:\n{doc}\n")
        return "\n".join(docs)

    def _extract_code(self, response: str) -> str:
        code_pattern = r'```python\s*(.*?)\s*```'
        matches = re.findall(code_pattern, response, re.DOTALL)
        return matches[0] if matches else response

    def _execute_plan(self, plan: dict, query: str) -> Generator[Dict[str, Any], None, None]:
        logger.info(f"执行步骤: {plan['description']}")
        yield {"type": "message", "content": f"执行步骤: {plan['description']}"}
        step_code, prompt = self._generate_step_code(plan, query)
        yield from self._execute_code(step_code, prompt)

    def _generate_step_code(self, step: dict, query: str) -> tuple:
        logger.info("正在生成步骤代码...")
        functions_docs = self._get_functions_docs(step['functions'])

        prompt = f"""
        根据以下步骤信息和函数文档，生成可执行的Python代码：

        总查询需求: {query}
        步骤描述：{step['description']}
        伪代码：{step['pseudocode']}
        注意事项: {step["tip_help"]}

        stock_data_provider可用函数文档：
        {functions_docs}

        请生成完整的、可执行的Python代码来完成这个步骤。确保代码可以直接运行，并遵循以下规则：
        1. 在代码开头添加：
        ```python
        from core.utils.code_tools import code_tools
        stock_data_provider = code_tools["stock_data_provider"]
        llm_client = code_tools["llm_client"]
        ```
        2. 使用 stock_data_provider 来调用数据提供函数
        3. 使用 llm_client.one_chat(prompt) 来调用 LLM 进行分析
        4. 仅使用"stock_data_provider可用函数文档"中提供的函数来获取数据
        5. 确保在代码的最后使用 code_tools.add("output_result", final_result) 来存储最终结果

        对于涉及 LLM 分析的部分，即便伪代码没有提及，也需要确保：
        1. 构建详细的提示词，包含所有必要的数据和上下文信息。
        2. 明确指定 LLM 输出应为 JSON 格式。
        3. 在提示词中包含具体的评分标准、推荐理由长度限制和风险因素识别要求。
        4. 提示词中包含了"模板"中所要求的内容。

        请只提供 Python 代码，不需要其他解释。
        """
        code_response = self.llm_client.one_chat(prompt)
        logger.info("步骤代码生成完成")
        return self._extract_code(code_response), prompt

    def _execute_code(self, code: str, prompt: str, max_attempts: int = 8) -> Generator[Dict[str, Any], None, None]:
        logger.info("正在执行代码...")
        attempt = 1
        while attempt <= max_attempts:
            try:
                result = self.code_runner.run(code)
                if result['error']:
                    if attempt < max_attempts:
                        logger.warning(f"代码执行出错（尝试 {attempt}/{max_attempts}），正在修复...")
                        yield {"type": "message", "content": f"代码执行出错，正在修复...（尝试 {attempt}/{max_attempts}）"}
                        code = self._fix_runtime_error(code, result['error'], prompt)
                        attempt += 1
                    else:
                        logger.error(f"代码执行失败，已达到最大尝试次数 ({max_attempts})。最后一次错误: {result['error']}")
                        yield {"type": "message", "content": f"代码执行失败，错误: {result['error']}"}
                        return
                else:
                    logger.info(f"代码执行成功（尝试 {attempt}/{max_attempts}）")
                    yield {"type": "message", "content": "代码执行成功，正在生成结果..."}
                    if 'output_result' in code_tools:
                        result = code_tools['output_result']
                        yield from self._format_result(result)
                    else:
                        yield {"type": "message", "content": "未能获取查询结果"}
                    return
            except Exception as e:
                if attempt < max_attempts:
                    logger.warning(f"执行代码时发生异常（尝试 {attempt}/{max_attempts}）: {str(e)}，正在尝试修复...")
                    yield {"type": "message", "content": f"执行代码时发生异常，正在修复...（尝试 {attempt}/{max_attempts}）"}
                    code = self._fix_runtime_error(code, str(e), prompt)
                    attempt += 1
                else:
                    logger.error(f"代码执行失败，已达到最大尝试次数 ({max_attempts})。最后一次错误: {str(e)}")
                    yield {"type": "message", "content": f"代码执行失败，错误: {str(e)}"}
                    return

        logger.error(f"代码执行失败，已达到最大尝试次数 ({max_attempts})。")
        yield {"type": "message", "content": "代码执行失败，请稍后重试。"}

    def _fix_runtime_error(self, code: str, error: str, prompt: str) -> str:
        logger.info("正在修复运行时错误...")
        fix_prompt = f"""
        执行以下代码时发生了错误：

        {code}

        错误信息：
        {error}

        原始提示词：
        {prompt}

        请修正代码以解决这个错误。请只提供修正后的完整代码，不需要其他解释。
        确保代码遵循原始提示词中的所有要求和规则，特别是：
        1. 使用 llm_client.one_chat(prompt) 来调用 LLM 进行分析（不使用 SSE）
        2. 对于 LLM 分析步骤，确保提示词详细且符合要求
        3. 使用 code_tools.add("output_result", final_result) 来存储最终结果
        """
        fixed_code_response = self.llm_client.one_chat(fix_prompt)
        logger.info("错误修复代码生成完成")
        return self._extract_code(fixed_code_response)

    def _format_result(self, result: str) -> Generator[Dict[str, Any], None, None]:
        markdown_prompt = f"""
        请将以下查询结果转换为清晰、结构化的Markdown格式：

        结果:
        {result}

        请确保:
        1. 使用适当的Markdown标记（如标题、列表、表格等）来组织信息。
        2. 保留所有重要信息，但以更易读的方式呈现。
        3. 如果结果中包含数字数据，考虑使用表格形式展示。
        4. 为主要部分添加简短的解释或总结。
        5. 如果有多个部分，使用适当的分隔和标题。

        请直接返回Markdown格式的文本，无需其他解释。
        """
        markdown_result = self.llm_client.one_chat(markdown_prompt)
        yield {"type": "message", "content": markdown_result}