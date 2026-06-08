from setuptools import setup, find_packages

setup(
    name='carbon-tool',
    version='1.0.0',
    description='碳中和管理命令行工具 - 用于企业排放数据的批量整理与分析',
    author='Energy Analyst Toolkit',
    packages=find_packages(),
    install_requires=[
        'click>=8.0.0',
        'pandas>=1.3.0',
        'openpyxl>=3.0.0',
        'pyyaml>=6.0',
        'tabulate>=0.8.0',
    ],
    entry_points={
        'console_scripts': [
            'carbon-tool=carbon_tool.cli:cli',
        ],
    },
    python_requires='>=3.8',
)
