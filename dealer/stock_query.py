import json
from core.utils.code_tools import code_tools
from core.interpreter.ast_code_runner import ASTCodeRunner
import re
from .plan_template_manager import PlanTemplateManager
from core.utils.log import logger


class StockQuery:
    def __init__(self, llm_client, stock_data_provider):
        self.llm_client = llm_client
        self.stock_data_provider = stock_data_provider
        self.code_runner = ASTCodeRunner()
        self.template_manager = PlanTemplateManager(llm_client)
        self.template_manager.load_templates_from_file("./json/stock_flows.md")
        code_tools.add_var('stock_data_provider', self.stock_data_provider)
        code_tools.add_var('llm_client', self.llm_client) 

    def query(self, query: str) -> str:
        logger.info(f"开始处理查询: {query}")
        plan = self._generate_plan(query)
        result = self._execute_plan(plan, query)
        logger.info("查询处理完成")
        return result

    def _generate_plan(self, query: str) -> list:
        logger.info("正在生成执行计划...")
        provider_description = self.stock_data_provider.get_self_description()
        best_template = self.template_manager.get_best_template(query)
        
        prompt = f"""
        根据以下查询要求生成一个执行计划：
        {query}

        可用的数据提供函数如下：
        {provider_description}

        基于以下模板生成计划：
        {best_template['template']}

        请生成一个包含多个步骤的执行计划。计划应该是一个 JSON 格式的数组，每个步骤应包含以下字段：
        1. "description": 需要完成的任务描述
        2. "pseudocode": 完成任务的伪代码
        3. "tip_hlep": 这个步骤的提示，或者注意事项，比如 提示词中要求llm_client的输出为json，以便后续进行解析
        4. "functions": 需要使用的数据提供函数列表
        5. "input_vars": 该步骤需要的输入变量列表，每个变量包含 "name" 和 "description"
        6. "output_vars": 该步骤产生的输出变量列表，每个变量包含 "name" 和 "description"

        请返回一个格式化的 JSON 计划，并用 ```json ``` 包裹。
        """
        plan_response = self.llm_client.one_chat(prompt)
        plan = self._parse_plan(plan_response)
        logger.info(f"执行计划生成完成，共 {len(plan)} 个步骤")
        return plan
    
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

    def _execute_plan(self, plan: list, query: str) -> str:
        for i, step in enumerate(plan, 1):
            logger.info(f"执行步骤 {i}/{len(plan)}: {step['description']}")
            step_code = self._generate_step_code(step, query,i,len(plan))
            self._execute_code(step_code)

        logger.info("所有步骤执行完成")
        
        # 获取最后一个步骤的结果
        if 'output_result' in code_tools:
            result = code_tools['output_result']
            logger.info(f"查询结果: {result}")
            return result
        else:
            logger.warning("未找到查询结果")
            return "未能获取查询结果"

    def _generate_step_code(self, step: dict, query: str,step_number:int,total_steps:int) -> str:
        logger.info("正在生成步骤代码...")
        is_last_step = step_number == total_steps
        functions_docs = self._get_functions_docs(step['functions'])

        sumaries=[code_tools[f"{item['name']}_summary"] for item in step["input_vars"] ]
        prompt = f"""
        根据以下步骤信息和函数文档，生成可执行的Python代码：

        总查询需求: {query}
        当前步骤:{step_number}/{total_steps}
        步骤描述：{step['description']}
        伪代码：{step['pseudocode']}
        注意事项: {step["tip_help"]}

        输入变量：
        {json.dumps(step['input_vars'], indent=2)}

        输出变量：
        {json.dumps(step['output_vars'], indent=2)}

        输出变量的结构描述：
        {sumaries}

        stock_data_provider可用函数文档：
        {functions_docs}

        请生成完整的、可执行的Python代码来完成这个步骤。确保代码可以直接运行，并遵循以下规则：
        1. 在代码开头添加：
        ```python
        from core.utils.code_tools import code_tools
        stock_data_provider = code_tools["stock_data_provider"]
        llm_client = code_tools["llm_client"]
        ```
        2. 使用 value = code_tools[name] 来读取输入变量
        3. 使用 code_tools.add(name, value) 来存储输出变量
        4. 使用 stock_data_provider 来调用数据提供函数
        5. 使用 llm_client.one_chat(prompt) 来调用 LLM 进行分析
        6. 仅使用"stock_data_provider可用函数文档"中提供的函数来获取数据
        7. 确保使用code_tools.add(name, value)保存了需要输出的变量
        8. {"如果这是最后一个步骤，请确保将最终结果存储在 'output_result' 变量中，使用 code_tools.add('output_result', final_result)" if is_last_step else ""}

        请只提供 Python 代码，不需要其他解释。
        """
        code = self.llm_client.one_chat(prompt)
        logger.info("步骤代码生成完成")
        return self._extract_code(code)

    def _execute_code(self, code: str) -> None:
        try:
            logger.info("正在执行代码...")
            result = self.code_runner.run(code)
            if result['error']:
                logger.warning("代码执行出错，正在修复...")
                fixed_code = self._fix_runtime_error(code, result['error'])
                self.code_runner.run(fixed_code)
                logger.info("错误修复完成，代码重新执行成功")
            else:
                logger.info("代码执行成功")
        except Exception as e:
            logger.error(f"执行代码时发生错误: {str(e)}")

    def _fix_runtime_error(self, code: str, error: str) -> str:
        logger.info("正在修复运行时错误...")
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
        logger.info("错误修复代码生成完成")
        return self._extract_code(fixed_code)