# Databricks notebook source
# Title: Bulk Edit UI for gc_prod_sandbox.su_eric_regna.metarisk_releases_dim (Optimized)

# COMMAND ----------

# Install the required library. ipydatagrid is the key to making this performant.
%pip install ipydatagrid

# COMMAND ----------

import pyspark.sql.functions as F
from pyspark.sql.types import *
import pandas as pd
import ipywidgets as widgets
import ipydatagrid
from IPython.display import display

# --- Configuration ---
TABLE_PATH = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"
EDITABLE_COLUMNS = ["start_date", "Status", "Callouts", "Product"]
KEY_COLUMN = "surrogate_key"  # Primary key for merging

# Dropdown options
STATUS_OPTIONS = ["Not Started", "On-Track", "At-Risk", "Off-Track", "Completed", "Blocked"]
PRODUCT_OPTIONS = ["MR Desktop", "MR Online", "Data", "Support", "MR Live"]

# This dictionary will store the changes made by the user
# Format: {(row_index, col_name): new_value}
changed_cells = {}

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 1: Load Data
# MAGIC Loading data from the Delta table.

# COMMAND ----------

try:
    spark_df = spark.table(TABLE_PATH)
    pandas_df = spark_df.toPandas()
    # Ensure a consistent order for display
    pandas_df = pandas_df.sort_values(by=KEY_COLUMN).reset_index(drop=True)
    
    print(f"✅ Successfully loaded {len(pandas_df)} records from {TABLE_PATH}")
except Exception as e:
    print(f"❌ Error loading table: {e}")
    dbutils.notebook.exit("Stopping notebook due to data loading error.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2: Edit Your Data
# MAGIC Use the table below to make your changes. The `start_date`, `Status`, `Callouts`, and `Product` columns are editable.

# COMMAND ----------

# --- Create the Editable Grid ---

# Define special cell renderers for dropdowns and dates
text_renderer = ipydatagrid.TextRenderer
dropdown_status_renderer = ipydatagrid.DropdownRenderer(options=STATUS_OPTIONS)
dropdown_product_renderer = ipydatagrid.DropdownRenderer(options=PRODUCT_OPTIONS)
date_renderer = ipydatagrid.DateRenderer()

# Create a dictionary to map columns to their renderers
renderers = {}
for col in pandas_df.columns:
    if col not in EDITABLE_COLUMNS:
        # Make non-editable columns read-only
        renderers[col] = ipydatagrid.TextRenderer(read_only=True)
    elif col == "Status":
        renderers[col] = dropdown_status_renderer
    elif col == "Product":
        renderers[col] = dropdown_product_renderer
    elif col == "start_date":
        renderers[col] = date_renderer
    else: # Callouts and any other editable text field
        renderers[col] = text_renderer()

# Create the grid
grid = ipydatagrid.DataGrid(
    dataframe=pandas_df,
    editable=True,
    renderers=renderers,
    layout={'height': '400px'} # Adjust height as needed
)

# --- Track Changes ---
def on_cell_changed(change):
    """Callback function to record a change made in the grid."""
    # The change event provides the row index, column name, and new value
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
            # Create a DataFrame from the detected changes
            updates = []
            for (row_index, col_name), new_value in changed_cells.items():
                surrogate_key = pandas_df.loc[row_index, KEY_COLUMN]
                updates.append({KEY_COLUMN: surrogate_key, "column": col_name, "value": new_value})

            updates_df = pd.DataFrame(updates)

            # Pivot the changes into a DataFrame with one row per updated record
            pivoted_updates = updates_df.pivot(index=KEY_COLUMN, columns='column', values='value').reset_index()

            # Merge with original data to fill in unchanged editable columns
            original_keys = pandas_df[[KEY_COLUMN] + EDITABLE_COLUMNS]
            final_updates_pd = pd.merge(pivoted_updates, original_keys, on=KEY_COLUMN, how='left', suffixes=('_new', ''))

            # Coalesce new and old values
            for col in EDITABLE_COLUMNS:
                if col + '_new' in final_updates_pd.columns:
                     final_updates_pd[col] = final_updates_pd[col + '_new'].fillna(final_updates_pd[col])
                
            # Select only the key and editable columns for the merge
            merge_data = final_updates_pd[[KEY_COLUMN] + EDITABLE_COLUMNS]

            # Convert to Spark DataFrame
            updates_spark_df = spark.createDataFrame(merge_data)
            updates_spark_df.createOrReplaceTempView("updates_to_merge")
            
            # --- Perform MERGE ---
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
            # Fetch the number of updated rows from the merge operation's result
            num_updated = result.select(F.sum("num_updated_rows").alias("total_updated")).first()['total_updated']

            print(f"✅ Success! {num_updated} record(s) were updated in {TABLE_PATH}.")
            
            # Clear changes and reload grid for next run
            changed_cells.clear()
            
            # Optional: Refresh the grid in-place by resetting its data
            # new_spark_df = spark.table(TABLE_PATH)
            # grid.data = new_spark_df.toPandas().sort_values(by=KEY_COLUMN).reset_index(drop=True)


        except Exception as e:
            import traceback
            print(f"❌ An error occurred during the update:")
            traceback.print_exc()

update_button.on_click(on_update_button_clicked)

display(update_button, output_area)

# COMMAND ----------
