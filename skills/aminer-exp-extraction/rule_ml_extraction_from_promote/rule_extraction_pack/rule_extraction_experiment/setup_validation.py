"""
规则提取实验框架设置验证脚本
Rule Extraction Experiment Framework Setup Validation Script

用于验证框架的基本结构和配置是否正确
Used to validate the basic structure and configuration of the framework
"""

import sys
from pathlib import Path
import json


def validate_directory_structure():
    """
    验证目录结构
    Validate directory structure

    伪代码 Pseudocode:
    1. 定义预期的目录结构
       Define expected directory structure
    2. 检查每个目录是否存在
       Check if each directory exists
    3. 检查关键文件是否存在
       Check if key files exist
    4. 返回验证结果
       Return validation result
    """
    # 伪代码实现 - Pseudocode implementation
    base_path = Path(__file__).parent

    # 预期目录 - Expected directories
    expected_dirs = [
        "common",
        "configs",
        "results",
        "runners"
    ]

    # 预期文件 - Expected files
    expected_files = [
        "common/__init__.py",
        "common/evaluator.py",
        "common/field_comparator.py",
        "common/metrics.py",
        "common/report_generator.py",
        "configs/sample_size.json",
        "configs/domain.json",
        "configs/experiment_type.json",
        "runners/sample_size_runner.py",
        "runners/domain_runner.py",
        "runners/experiment_type_runner.py",
        "README.md",
        "__init__.py"
    ]

    validation_results = {
        "directories": {},
        "files": {},
        "overall_status": "passed"
    }

    print("🔍 Validating Directory Structure...")

    # 验证目录 - Validate directories
    for dir_name in expected_dirs:
        dir_path = base_path / dir_name
        exists = dir_path.exists() and dir_path.is_dir()
        validation_results["directories"][dir_name] = exists
        status = "✅" if exists else "❌"
        print(f"{status} Directory: {dir_name}")

    # 验证文件 - Validate files
    for file_path in expected_files:
        file_full_path = base_path / file_path
        exists = file_full_path.exists() and file_full_path.is_file()
        validation_results["files"][file_path] = exists
        status = "✅" if exists else "❌"
        print(f"{status} File: {file_path}")

    # 检查总体状态 - Check overall status
    all_dirs_valid = all(validation_results["directories"].values())
    all_files_valid = all(validation_results["files"].values())

    if not all_dirs_valid or not all_files_valid:
        validation_results["overall_status"] = "failed"

    return validation_results


def validate_configurations():
    """
    验证配置文件
    Validate configuration files

    伪代码 Pseudocode:
    1. 遍历所有配置文件
       Iterate through all configuration files
    2. 验证JSON格式
       Validate JSON format
    3. 验证必要字段
       Validate required fields
    4. 返回验证结果
       Return validation result
    """
    # 伪代码实现 - Pseudocode implementation
    base_path = Path(__file__).parent
    configs_dir = base_path / "configs"

    validation_results = {
        "configs": {},
        "overall_status": "passed"
    }

    print("\n🔍 Validating Configuration Files...")

    # 必要字段 - Required fields
    required_fields = [
        "experiment_id",
        "field_name",
        "field_type",
        "test_set",
        "gold_set",
        "rule_module",
        "rule_class",
        "data_paths",
        "metrics"
    ]

    for config_file in configs_dir.glob("*.json"):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 验证必要字段 - Validate required fields
            missing_fields = [field for field in required_fields if field not in config]
            is_valid = len(missing_fields) == 0

            validation_results["configs"][config_file.name] = {
                "valid": is_valid,
                "missing_fields": missing_fields if missing_fields else None
            }

            status = "✅" if is_valid else "❌"
            print(f"{status} Config: {config_file.name}")

            if not is_valid:
                print(f"   Missing fields: {', '.join(missing_fields)}")

        except json.JSONDecodeError as e:
            validation_results["configs"][config_file.name] = {
                "valid": False,
                "error": f"JSON decode error: {str(e)}"
            }
            print(f"❌ Config: {config_file.name} - Invalid JSON format")
        except Exception as e:
            validation_results["configs"][config_file.name] = {
                "valid": False,
                "error": str(e)
            }
            print(f"❌ Config: {config_file.name} - Error: {str(e)}")

    # 检查总体状态 - Check overall status
    all_configs_valid = all(result["valid"] for result in validation_results["configs"].values())

    if not all_configs_valid:
        validation_results["overall_status"] = "failed"

    return validation_results


def validate_python_imports():
    """
    验证Python模块导入
    Validate Python module imports

    伪代码 Pseudocode:
    1. 尝试导入主要模块
       Try to import main modules
    2. 验证主要类是否可导入
       Validate if main classes can be imported
    3. 返回验证结果
       Return validation result
    """
    # 伪代码实现 - Pseudocode implementation
    validation_results = {
        "modules": {},
        "overall_status": "passed"
    }

    print("\n🔍 Validating Python Imports...")

    # 添加项目根目录到路径 - Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # 要验证的模块和类 - Modules and classes to validate
    modules_to_validate = [
        ("rule_extraction_experiment.common", "common"),
        ("rule_extraction_experiment.common.evaluator", "evaluator"),
        ("rule_extraction_experiment.common.field_comparator", "field_comparator"),
        ("rule_extraction_experiment.common.metrics", "metrics"),
        ("rule_extraction_experiment.common.report_generator", "report_generator"),
    ]

    for module_name, short_name in modules_to_validate:
        try:
            __import__(module_name)
            validation_results["modules"][short_name] = True
            print(f"✅ Module: {short_name}")
        except ImportError as e:
            validation_results["modules"][short_name] = False
            print(f"❌ Module: {short_name} - Import error: {str(e)}")

    # 检查总体状态 - Check overall status
    all_modules_valid = all(validation_results["modules"].values())

    if not all_modules_valid:
        validation_results["overall_status"] = "failed"

    return validation_results


def print_summary(directory_validation: dict, config_validation: dict, import_validation: dict):
    """
    打印验证摘要
    Print validation summary

    伪代码 Pseudocode:
    1. 汇总所有验证结果
       Summarize all validation results
    2. 检查是否有失败项
       Check if there are any failures
    3. 打印总体状态
       Print overall status
    4. 提供下一步建议
       Provide next step suggestions
    """
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)

    # 汇总状态 - Summary status
    directory_status = directory_validation["overall_status"]
    config_status = config_validation["overall_status"]
    import_status = import_validation["overall_status"]

    # 打印各项状态 - Print each status
    print(f"\n📁 Directory Structure: {'✅ PASSED' if directory_status == 'passed' else '❌ FAILED'}")
    print(f"📝 Configuration Files: {'✅ PASSED' if config_status == 'passed' else '❌ FAILED'}")
    print(f"🐍 Python Imports: {'✅ PASSED' if import_status == 'passed' else '❌ FAILED'}")

    # 总体状态 - Overall status
    all_passed = all([
        directory_status == "passed",
        config_status == "passed",
        import_status == "passed"
    ])

    if all_passed:
        print("\n" + "="*70)
        print("🎉 ALL VALIDATIONS PASSED!")
        print("="*70)
        print("\n✨ The rule extraction experiment framework is ready to use!")
        print("\nNext Steps:")
        print("1. Run sample_size experiment:")
        print("   python rule_extraction_experiment/runners/sample_size_runner.py")
        print("2. Run domain experiment:")
        print("   python rule_extraction_experiment/runners/domain_runner.py")
        print("3. Run experiment_type experiment:")
        print("   python rule_extraction_experiment/runners/experiment_type_runner.py")
    else:
        print("\n" + "="*70)
        print("⚠️ SOME VALIDATIONS FAILED")
        print("="*70)
        print("\nPlease check the failed items above and fix them before using the framework.")


def main():
    """
    主函数 - Main function
    """
    print("🚀 Rule Extraction Experiment Framework Setup Validation")
    print("="*70)

    # 运行所有验证 - Run all validations
    directory_validation = validate_directory_structure()
    config_validation = validate_configurations()
    import_validation = validate_python_imports()

    # 打印摘要 - Print summary
    print_summary(directory_validation, config_validation, import_validation)

    # 退出码 - Exit code
    all_passed = all([
        directory_validation["overall_status"] == "passed",
        config_validation["overall_status"] == "passed",
        import_validation["overall_status"] == "passed"
    ])

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)