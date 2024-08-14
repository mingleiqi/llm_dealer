import ast
import sys
import io
import os
from typing import Any, Dict, Generator, Optional, Callable
import traceback
from tqdm import tqdm

import ast
import sys
import io
import os
from typing import Any, Dict, Optional, Callable
import traceback
from tqdm import tqdm
import time


class StepCodeRunner:
    def __init__(self, debug=False):
        self.debug = debug
        self.last_update_time = 0
        self.update_interval = 0.1  # 更新间隔，秒

    def run_sse(self, code: str, global_vars: Dict[str, Any] = {}) -> Generator[Dict[str, Any], None, None]:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_error

        result = {
            "output": "",
            "error": None,
            "updated_vars": {},
            "debug": None
        }

        exec_globals = global_vars.copy()

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            yield {"type": "error", "content": f"Syntax error in code: {str(e)}"}
            return

        total_lines = len(tree.body)
        executed_lines = 0

        def progress_update():
            nonlocal executed_lines
            executed_lines += 1
            progress = min(executed_lines / total_lines, 1.0)
            return {"type": "progress", "content": progress}

        try:
            if self.debug:
                yield {"type": "debug", "content": f"调试信息: 准备执行下面的代码:\n{code}"}

            self.check_security(tree)

            for node in ast.walk(tree):
                if isinstance(node, ast.stmt):
                    exec(compile(ast.Module([node], type_ignores=[]), filename="<ast>", mode="exec"), exec_globals)
                    current_time = time.time()
                    if current_time - self.last_update_time >= self.update_interval:
                        yield progress_update()
                        self.last_update_time = current_time

        except Exception as e:
            error_msg = f"Uncaught exception: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            yield {"type": "error", "content": error_msg}
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            result["output"] = redirected_output.getvalue()
            if result["output"]:
                yield {"type": "output", "content": result["output"]}

            error_output = redirected_error.getvalue()
            if error_output:
                yield {"type": "error", "content": f"Captured stderr:\n{error_output}"}

            result["updated_vars"] = {k: v for k, v in exec_globals.items() if k not in global_vars or global_vars[k] is not v}
            yield {"type": "result", "content": result}

    def run(self, code: str, global_vars: Dict[str, Any] = {}, progress_callback: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_error

        result = {
            "output": "",
            "error": None,
            "updated_vars": {},
            "debug": None
        }

        tree = ast.parse(code)
        total_lines = len(tree.body)
        
        self.progress_bar = tqdm(total=total_lines, desc="Executing", unit="lines", file=sys.__stderr__)

        def trace_calls(frame, event, arg):
            if event == 'line':
                current_time = time.time()
                if current_time - self.last_update_time >= self.update_interval:
                    self.progress_bar.update(1)
                    if progress_callback:
                        progress_callback(self.progress_bar.n / total_lines)
                    self.last_update_time = current_time
            return trace_calls

        try:
            if self.debug:
                result["debug"] = f"调试信息: 准备执行下面的代码:\n{code}"

            self.check_security(tree)

            exec_globals = global_vars.copy()
            
            sys.settrace(trace_calls)
            exec(code, exec_globals)
            sys.settrace(None)

            result["output"] = redirected_output.getvalue()
            result["updated_vars"] = {k: v for k, v in exec_globals.items() if k not in global_vars or global_vars[k] is not v}

        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["error"] += f"\n{redirected_error.getvalue()}"
            result["error"] += traceback.format_exc()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            if self.progress_bar:
                self.progress_bar.close()

        return result

    def check_security(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'remove' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os':
                    raise SecurityException("禁止删除文件")
                if node.func.attr == 'rename' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os':
                    raise SecurityException("禁止重命名文件")

    def safe_open(self, file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        abs_path = os.path.abspath(file)
        if not abs_path.startswith(os.path.abspath('.')):
            raise SecurityException(f"禁止访问 ./ 目录以外的文件: {file}")
        
        if 'w' in mode or 'a' in mode or '+' in mode:
            raise SecurityException(f"禁止写入或修改文件: {file}")
        
        return open(file, mode, buffering, encoding, errors, newline, closefd, opener)



class SubStepCodeRunner:
    def __init__(self, debug=False):
        self.debug = debug

    def run(self, code: str, global_vars: Dict[str, Any] = {}, progress_callback: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_error

        result = {
            "output": "",
            "error": None,
            "updated_vars": {},
            "debug": None
        }

        try:
            if self.debug:
                result["debug"] = f"调试信息: 准备执行下面的代码:\n{code}"

            tree = ast.parse(code)
            self.check_security(tree)

            # 插入进度更新代码
            modified_tree = self.insert_progress_updates(tree, progress_callback)

            exec_globals = global_vars.copy()
            
            # 执行修改后的代码
            exec(compile(modified_tree, '<string>', 'exec'), exec_globals)

            # 捕获输出
            result["output"] = redirected_output.getvalue()

            # 返回更新后的变量
            result["updated_vars"] = {k: v for k, v in exec_globals.items() if k not in global_vars or global_vars[k] is not v}

        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["error"] += f"\n{redirected_error.getvalue()}"
            result["error"] += traceback.format_exc()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return result

    def insert_progress_updates(self, tree, progress_callback):
        total_nodes = sum(1 for _ in ast.walk(tree))
        progress = [0]

        def update_progress(node):
            progress[0] += 1
            if progress_callback:
                progress_callback(progress[0] / total_nodes)
            return node

        class ProgressInserter(ast.NodeTransformer):
            def generic_visit(self, node):
                node = update_progress(node)
                return super().generic_visit(node)

        return ProgressInserter().visit(tree)

    def check_security(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'remove' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os':
                    raise SecurityException("禁止删除文件")
                if node.func.attr == 'rename' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os':
                    raise SecurityException("禁止重命名文件")

    def safe_open(self, file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        abs_path = os.path.abspath(file)
        if not abs_path.startswith(os.path.abspath('.')):
            raise SecurityException(f"禁止访问 ./ 目录以外的文件: {file}")
        
        if 'w' in mode or 'a' in mode or '+' in mode:
            raise SecurityException(f"禁止写入或修改文件: {file}")
        
        return open(file, mode, buffering, encoding, errors, newline, closefd, opener)

class SecurityException(Exception):
    pass