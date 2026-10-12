import os
import sys
from pyspark.sql import SparkSession

def get_spark_session(app_name: str = "inventory-demand-pipeline") -> SparkSession:
    """
    Initializes and returns a configured SparkSession for local execution on Windows.
    Ensures winutils / HADOOP_HOME and Python worker paths are appropriately configured.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    hadoop_home = os.path.join(project_root, "hadoop")
    
    if os.path.exists(hadoop_home):
        os.environ["HADOOP_HOME"] = hadoop_home
        hadoop_bin = os.path.join(hadoop_home, "bin")
        if hadoop_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = hadoop_bin + ";" + os.environ.get("PATH", "")
            
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    spark = (
        SparkSession.builder
        .master("local[2]")
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.default.parallelism", "4")
        .config("spark.sql.execution.arrow.pyspark.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark
