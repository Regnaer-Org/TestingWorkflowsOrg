# Databricks notebook source
# Title: Bulk Edit UI for gc_prod_sandbox.su_eric_regna.metarisk_releases_dim (Final Hardened Version)
#
# What this does:
# - Provides a performant UI to bulk-edit a Delta table using ipydatagrid.
# - Dynamically creates dropdown options to prevent UI rendering errors.
# - Enforces a strict schema during the update process to prevent data type mismatch errors on MERGE.

# COMMAND ----------

# Install the required library
%pip install ipydatagrid

# COMMAND ----------

import pyspark.sql.functions as F
from pyspark.sql.types import StructType, StructField, StringType, DateType, LongType
import pandas as pd
import ipywidgets as widgets
import ipydatagrid
from IPython.display import display

# --- Configuration ---
TABLE_PATH = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"
EDITABLE_COLUMNS = ["start_date", "Status", "Callouts", "Product"]
KEY_COLUMN = "surrogate_key"

# Base options for the dropdowns
base_status_options = ["Not Started", "On-Track", "At-Risk", "Off-Track", "Completed", "Blocked"]
base_product_options = ["MR Desktop", "MR Online", "Data", "Support", "MR Live"]

# This dictionary will store the final state of changed cells
changed_cells = {}

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 1: Load Data & Prepare UI Components
# MAGIC Loading data and dynamically creating dropdown options to prevent rendering errors.

# COMMAND ----------

try:
    spark_df = spark.table(TABLE_PATH)
    
    # Dynamically create robust dropdown options to prevent errors
    existing_status = [row.Status for row in spark_df.select("Status").distinct().collect() if row.Status is not None]
    existing_product = [row.Product for row in spark_df.select("Product").distinct().collect() if row.Product is not None]

    # Combine predefined options with existing ones and add None to handle NULLs safely
    STATUS_OPTIONS = sorted(list(set(base_status_options + existing_status))) + [None]
    PRODUCT_OPTIONS = sorted(list(set(base_product_options + existing_product))) + [None]
    
    # Load the full DataFrame into pandas for the UI
    pandas_df = spark_df.toPandas()
    
    # Ensure date columns are proper datetime objects for the DateRenderer
    if 'start_date' in pandas_df.columns:
        pandas_df['start_date'] = pd.to_datetime(pandas_df['start_date'])

    pandas_df = pandas_df.sort_values(by=KEY_COLUMN).reset_index(drop=True)
    
    print(f"✅ Successfully loaded {len(pandas_df)} records.")

except Exception as e:
    print(f"❌ Error during data loading or dropdown preparation: {e}")
    dbutils.notebook.exit("Stopping notebook due to error.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2: Edit Your Data
# MAGIC Use the table below to make your changes.

# COMMAND ----------

# --- Create the Editable Grid ---
dropdown_status_renderer = ipydatagrid.DropdownRenderer(options=STATUS_OPTIONS)
dropdown_product_renderer = ipydatagrid.DropdownRenderer(options=PRODUCT_OPTIONS)

renderers = {
    col: (
        ipydatagrid.TextRenderer(read_only=True) if col not in EDITABLE_COLUMNS else
        dropdown_status_renderer if col == "Status" else
        dropdown_product_renderer if col == "Product" else
        ipydatagrid.DateRenderer() if col == "start_date" else
        ipydatagrid.TextRenderer()
    )
    for col in pandas_df.columns
}

grid = ipydatagrid.DataGrid(
    dataframe=pandas_df,
    editable=True,
    renderers=renderers,
    layout={'height': '400px'}
)

def on_cell_changed(change):
    """Callback to record a change."""
    changed_cells[(change['row'], change['column'])] = change['value']

grid.on_cell_changed(on_cell_changed)
display(grid)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 3: Apply Updates
# MAGIC Click the button below to merge your changes into the table.

# COMMAND ----------

update_button = widgets.Button(description="Update Table", button_style='success')
output_area = widgets.Output()

def on_update_button_clicked(b):
    with output_area:
        output_area.clear_output()
        
        if not changed_cells:
            print("ℹ️ No changes detected. Nothing to update.")
            return

        print(f"Processing {len(changed_cells)} changed cell(s)...")

        try:
            # Identify the full rows that have at least one change
            changed_row_indices = sorted(list(set(idx for idx, col in changed_cells.keys())))
            if not changed_row_indices:
                print("ℹ️ No effective changes detected.")
                return
            
            # Create a clean copy of the changed rows to avoid side effects
            final_updates_pd = pandas_df.iloc[changed_row_indices].copy()

            # Apply the edits to this smaller DataFrame
            for (row_index, col_name), new_value in changed_cells.items():
                # Find the correct position in the smaller `final_updates_pd`
                if row_index in final_updates_pd.index:
                    final_updates_pd.loc[row_index, col_name] = new_value

            # --- CONFIRMED BEST PRACTICE: Define a strict schema for the Spark DataFrame ---
            # This prevents type inference errors (e.g., date as string) during the MERGE.
            # The schema must match the columns and types required for the MERGE statement.
            merge_schema = StructType([
                StructField(KEY_COLUMN, LongType(), False),
                StructField("start_date", DateType(), True),
                StructField("Status", StringType(), True),
                StructField("Callouts", StringType(), True),
                StructField("Product", StringType(), True),
            ])
            
            # Select only the necessary columns for the merge operation
            merge_data = final_updates_pd[[KEY_COLUMN] + EDITABLE_COLUMNS]

            # Create the Spark DataFrame using the explicit schema to ensure type safety
            updates_spark_df = spark.createDataFrame(merge_data, schema=merge_schema)
            updates_spark_df.createOrReplaceTempView("updates_to_merge")
            
            # --- Perform MERGE ---
            # The target column names (e.g., target.start_date) must match the physical table schema.
            merge_sql = f"""
                MERGE INTO {TABLE_PATH} AS target
                USING updates_to_merge AS source
                ON target.{KEY_COLUMN} = source.{KEY_COLUMN}
                WHEN MATCHED THEN UPDATE SET
                    target.start_date = source.start_date,
                    target.Status = source.Status,
                    target.Callouts = source.Callouts,
                    target.Product = source.Product
            """
            
            result = spark.sql(merge_sql)
            # The result of MERGE in Databricks includes metrics about the operation
            num_updated = result.select(F.sum("num_updated_rows").alias("total_updated")).first()['total_updated']

            print(f"✅ Success! {num_updated} record(s) were updated in {TABLE_PATH}.")
            
            # Clear changes for the next run
            changed_cells.clear()

        except Exception as e:
            import traceback
            print(f"❌ An error occurred during the update:")
            traceback.print_exc()

update_button.on_click(on_update_button_clicked)
display(update_button, output_area)
