import json
from core.utils.code_tools import code_tools
from core.interpreter.ast_code_runner import ASTCodeRunner
import re

class StockQuery:
    def __init__(self, llm_client, stock_data_provider):
        self.llm_client = llm_client
        self.stock_data_provider = stock_data_provider
        self.code_runner = ASTCodeRunner()

    def query(self, query: str) -> str:
        plan = self._generate_plan(query)
        result = self._execute_plan(plan, query)
        return result

    def _generate_plan(self, query: str) -> list:
        provider_description = self.stock_data_provider.get_self_description()
        prompt = f"""
        根据以下查询要求生成一个执行计划：
        {query}

        可用的数据提供函数如下：
        {provider_description}

        请生成一个包含多个步骤的执行计划。计划应该是一个 JSON 格式的数组，每个步骤应包含以下字段：
        1. "description": 需要完成的任务描述
        2. "code": 完成任务的伪代码
        3. "functions": 需要使用的数据提供函数列表
        4. "input_vars": 该步骤需要的输入变量列表，每个变量包含 "name" 和 "description"
        5. "output_vars": 该步骤产生的输出变量列表，每个变量包含 "name" 和 "description"

        确保计划涵盖以下方面：
        1. 筛选相关股票
        2. 获取必要的市场、财务、新闻或历史数据
        3. 使用LLM进行数据分析和评分
        4. 汇总结果并得出最终结论

        请返回一个格式化的 JSON 计划，并用 ```json ``` 包裹。
        """
        plan_response = self.llm_client.one_chat(prompt)
        return self._parse_plan(plan_response)

    def _parse_plan(self, plan_response: str) -> list:
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

    def _execute_plan(self, plan: list, query: str) -> None:
        for i, step in enumerate(plan):
            step_code = self._generate_step_code(step, query, i == len(plan) - 1)
            self._execute_code(step_code)

    def _generate_step_code(self, step: dict, query: str, is_last_step: bool) -> str:
        functions_docs = self._get_functions_docs(step['functions'])
        prompt = f"""
        根据以下步骤信息和函数文档，生成可执行的Python代码：

        步骤描述：{step['description']}
        伪代码：{step['code']}
        查询要求：{query}

        输入变量：
        {json.dumps(step['input_vars'], indent=2)}

        输出变量：
        {json.dumps(step['output_vars'], indent=2)}

        可用函数文档：
        {functions_docs}

        请生成完整的、可执行的Python代码来完成这个步骤。确保代码可以直接运行，并遵循以下规则：
        1. 在代码开头添加：from core.utils.code_tools import code_tools
        2. 使用 code_tools[name] 来读取输入变量
        3. 使用 code_tools.add(name, value) 来存储输出变量
        4. 使用 stock_data_provider 来调用数据提供函数
        5. 使用 llm_client.one_chat() 来调用 LLM 进行分析
        6. {"如果这是最后一个步骤，请确保将最终结果存储在 'output_result' 变量中，使用 code_tools.add('output_result', final_result)" if is_last_step else ""}

        请只提供 Python 代码，不需要其他解释。
        """
        code = self.llm_client.one_chat(prompt)
        return self._extract_code(code)

    def _execute_code(self, code: str) -> None:
        try:
            code_tools.add_var('stock_data_provider', self.stock_data_provider)
            code_tools.add_var('llm_client', self.llm_client)
            result = self.code_runner.run(code)
            if result['error']:
                fixed_code = self._fix_runtime_error(code, result['error'])
                self.code_runner.run(fixed_code)
        except Exception as e:
            print(f"执行代码时发生错误: {str(e)}")

    def _fix_runtime_error(self, code: str, error: str) -> str:
        fix_prompt = f"""
        执行以下代码时发生了错误：

        {code}

        错误信息：
        {error}

        请修正代码以解决这个错误。请只提供修正后的完整代码，不需要其他解释。
        确保代码遵循以下规则：
        1. 在代码开头添加：from core.utils.code_tools import code_tools
        2. 使用 code_tools[name] 来读取输入变量
        3. 使用 code_tools.add(name, value) 来存储输出变量
        4. 使用 stock_data_provider 来调用数据提供函数
        5. 使用 llm_client.one_chat() 来调用 LLM 进行分析
        6. 如果这是最后一个步骤，请确保将最终结果存储在 'output_result' 变量中，使用 code_tools.add('output_result', final_result)
        """
        fixed_code = self.llm_client.one_chat(fix_prompt)
        return self._extract_code(fixed_code)