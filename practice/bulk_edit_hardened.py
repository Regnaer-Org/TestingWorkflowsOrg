# Databricks notebook source
# Title: Bulk Edit UI for gc_prod_sandbox.su_eric_regna.metarisk_releases_dim (Hardened Version)
#
# What this does:
# - Provides a performant UI to bulk-edit a Delta table using ipydatagrid.
# - Dynamically creates dropdown options to prevent UI rendering errors.
# - Enforces a strict schema during the update process to prevent data type mismatch errors on MERGE.
# - Hardening:
#   - Robust change event handling for ipydatagrid (newValue/value fallback).
#   - Avoid None in dropdown options via sentinel and convert back on submit.
#   - Strict type coercion for dates and key column.
#   - Safer MERGE result metrics via Delta history.
#   - Defensive validation and clearer error messages.

# COMMAND ----------

# Install the required library
%pip install ipydatagrid

# COMMAND ----------

import pyspark.sql.functions as F
from pyspark.sql.types import StructType, StructField, StringType, DateType, LongType
from delta.tables import DeltaTable

import pandas as pd
import ipywidgets as widgets
import ipydatagrid
from IPython.display import display

# --- Configuration ---
TABLE_PATH = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"
EDITABLE_COLUMNS = ["start_date", "Status", "Callouts", "Product"]
KEY_COLUMN = "surrogate_key"
NULL_SENTINEL = "<NULL>"

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

    # Validate required columns exist
    required_cols = [KEY_COLUMN] + EDITABLE_COLUMNS
    missing = [c for c in required_cols if c not in spark_df.columns]
    if missing:
        raise ValueError(f"Missing required column(s) in {TABLE_PATH}: {missing}")

    # Dynamically create robust dropdown options (exclude NULLs; handle with sentinel)
    existing_status = [r["Status"] for r in spark_df.select("Status").distinct().where(F.col("Status").isNotNull()).collect()]
    existing_product = [r["Product"] for r in spark_df.select("Product").distinct().where(F.col("Product").isNotNull()).collect()]

    STATUS_OPTIONS = sorted(set(base_status_options + existing_status)) + [NULL_SENTINEL]
    PRODUCT_OPTIONS = sorted(set(base_product_options + existing_product)) + [NULL_SENTINEL]

    # Load the full DataFrame into pandas for the UI
    pandas_df = spark_df.toPandas()

    # Ensure date columns are proper datetime objects for the DateRenderer
    if "start_date" in pandas_df.columns:
        pandas_df["start_date"] = pd.to_datetime(pandas_df["start_date"], errors="coerce")

    # Sort by key for stable indexing in grid
    pandas_df = pandas_df.sort_values(by=KEY_COLUMN).reset_index(drop=True)

    print(f"✅ Successfully loaded {len(pandas_df)} records and {pandas_df.shape[1]} columns from {TABLE_PATH}.")

except Exception as e:
    import traceback
    print(f"❌ Error during data loading or dropdown preparation: {e}")
    traceback.print_exc()
    dbutils.notebook.exit("Stopping notebook due to error.")

# COMMAND ----------
# MAGIC %md
# MAGIC ### Step 2: Edit Your Data
# MAGIC Use the table below to make your changes.

# COMMAND ----------

# Create the Editable Grid
dropdown_status_renderer = ipydatagrid.DropdownRenderer(options=STATUS_OPTIONS)
dropdown_product_renderer = ipydatagrid.DropdownRenderer(options=PRODUCT_OPTIONS)

renderers = {}
for col in pandas_df.columns:
    if col not in EDITABLE_COLUMNS:
        renderers[col] = ipydatagrid.TextRenderer(read_only=True)
    elif col == "Status":
        renderers[col] = dropdown_status_renderer
    elif col == "Product":
        renderers[col] = dropdown_product_renderer
    elif col == "start_date":
        renderers[col] = ipydatagrid.DateRenderer()
    else:
        renderers[col] = ipydatagrid.TextRenderer()

grid = ipydatagrid.DataGrid(
    dataframe=pandas_df,
    editable=True,
    renderers=renderers,
    layout={"height": "500px"},
)

def _coerce_to_date_or_none(v):
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, pd.Timestamp) and pd.isna(v)):
        return None
    # Handle strings or Timestamps
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()

def on_cell_changed(evt: dict):
    """
    Callback to record a change. Supports various ipydatagrid event payload keys.
    Expects keys: 'row', 'column', and 'newValue' (with fallback to 'value').
    """
    try:
        row = evt.get("row")
        col = evt.get("column")
        new_val = evt.get("newValue", evt.get("value"))

        if row is None or col is None:
            return

        # Map sentinel back to None
        if new_val == NULL_SENTINEL:
            new_val = None

        # Coerce date column
        if col == "start_date":
            new_val = _coerce_to_date_or_none(new_val)

        changed_cells[(row, col)] = new_val
    except Exception as e:
        print(f"⚠️ Failed to process cell change event: {e}")

# Register event listener (note: some versions use on_cell_change; on_cell_changed is preferred)
try:
    grid.on_cell_changed(on_cell_changed)
except Exception:
    # Fallback for environments exposing on_cell_change
    try:
        grid.on_cell_change(on_cell_changed)
    except Exception as e:
        print(f"⚠️ Could not attach change handler: {e}")

display(grid)

# COMMAND ----------
# MAGIC %md
# MAGIC ### Step 3: Apply Updates
# MAGIC Click the button below to merge your changes into the table.

# COMMAND ----------

update_button = widgets.Button(description="Update Table", button_style="success")
output_area = widgets.Output()

def on_update_button_clicked(_):
    with output_area:
        output_area.clear_output()

        if not changed_cells:
            print("ℹ️ No changes detected. Nothing to update.")
            return

        print(f"Processing {len(changed_cells)} changed cell(s)...")

        try:
            # Identify the full rows that have at least one change
            changed_row_indices = sorted(list({idx for (idx, _col) in changed_cells.keys()}))
            if not changed_row_indices:
                print("ℹ️ No effective changes detected.")
                return

            # Build a working frame with only key + editable columns
            work_cols = [KEY_COLUMN] + EDITABLE_COLUMNS
            final_updates_pd = pandas_df.loc[changed_row_indices, work_cols].copy()

            # Apply the edits to this smaller DataFrame
            for (row_index, col_name), new_value in changed_cells.items():
                if row_index in final_updates_pd.index and col_name in final_updates_pd.columns:
                    final_updates_pd.loc[row_index, col_name] = new_value

            # Type coercions and validations

            # 1) Key: non-nullable, integer-like
            if final_updates_pd[KEY_COLUMN].isna().any():
                raise ValueError(f"Null values found in key column '{KEY_COLUMN}'.")
            final_updates_pd[KEY_COLUMN] = pd.to_numeric(final_updates_pd[KEY_COLUMN], errors="raise").astype("int64")

            # 2) Date: ensure Python date objects for Spark DateType
            if "start_date" in final_updates_pd.columns:
                final_updates_pd["start_date"] = pd.to_datetime(final_updates_pd["start_date"], errors="coerce").dt.date

            # 3) Strings: normalize NaN to None
            for c in ["Status", "Callouts", "Product"]:
                if c in final_updates_pd.columns:
                    final_updates_pd[c] = final_updates_pd[c].where(~pd.isna(final_updates_pd[c]), None)
                    # Ensure not carrying sentinel accidentally
                    final_updates_pd[c] = final_updates_pd[c].apply(lambda x: None if x == NULL_SENTINEL else x)

            # Deduplicate by key in case of multiple edits on same row
            final_updates_pd = final_updates_pd.sort_index().drop_duplicates(subset=[KEY_COLUMN], keep="last")

            # Select only the necessary columns for the merge operation (column order must match schema below)
            merge_data = final_updates_pd[[KEY_COLUMN, "start_date", "Status", "Callouts", "Product"]]

            # Define a strict schema for the Spark DataFrame to prevent inference/casting issues
            merge_schema = StructType([
                StructField(KEY_COLUMN, LongType(), False),
                StructField("start_date", DateType(), True),
                StructField("Status", StringType(), True),
                StructField("Callouts", StringType(), True),
                StructField("Product", StringType(), True),
            ])

            # Create the Spark DataFrame using the explicit schema to ensure type safety
            updates_spark_df = spark.createDataFrame(merge_data, schema=merge_schema)
            updates_spark_df.createOrReplaceTempView("updates_to_merge")

            # Perform MERGE (update columns unconditionally on match)
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
            spark.sql(merge_sql)

            # Fetch operation metrics from Delta history
            dt = DeltaTable.forName(spark, TABLE_PATH)
            op_metrics = dt.history(1).select("operationMetrics").collect()[0][0] or {}

            # Try multiple possible keys depending on runtime version
            num_updated = (
                int(op_metrics.get("numTargetRowsUpdated") or 0)
                if "numTargetRowsUpdated" in op_metrics
                else int(op_metrics.get("numUpdatedRows") or 0)
            )

            print(f"✅ Success! {num_updated} record(s) were updated in {TABLE_PATH}.")

            # Clear changes for the next run
            changed_cells.clear()

        except Exception as e:
            import traceback
            print("❌ An error occurred during the update:")
            traceback.print_exc()

update_button.on_click(on_update_button_clicked)
display(update_button, output_area)
