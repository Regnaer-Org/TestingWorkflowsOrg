# Databricks notebook source
# MAGIC %md
# MAGIC # Bulk Edit UI (Paginated, Hardened, & Advanced Debugging)
# MAGIC 
# MAGIC This notebook provides a scalable UI to bulk-edit a Delta table.
# MAGIC 
# MAGIC ### Instructions
# MAGIC 1. **Run Cell 1**: This will set up all the functions and render the interactive grid UI.
# MAGIC 2. **Run Cell 2**: This attaches the final update logic to the "Apply Updates" button.
# MAGIC 3. **Edit Data**: Use the grid to make your changes. You can navigate through pages.
# MAGIC 4. **Apply Updates**: Click the "Apply Updates" button to merge your changes into the Delta table.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Cell 1: UI Setup and Rendering
# MAGIC This cell defines and renders all UI components. Run this cell first.

# COMMAND ----------

# Install the required library if it's not already on the cluster
%pip install ipydatagrid

# COMMAND ----------

import pyspark.sql.functions as F
from pyspark.sql.types import StructType, StructField, StringType, DateType, LongType
from delta.tables import DeltaTable
import pandas as pd
import ipywidgets as widgets
from ipywidgets import AppLayout, Layout
import ipydatagrid
from IPython.display import display, clear_output
import io
import traceback

# --- Configuration ---
TABLE_PATH = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"
EDITABLE_COLUMNS = ["start_date", "Status", "Callouts", "Product"]
KEY_COLUMN = "surrogate_key"
NULL_SENTINEL = "<NULL>"
PAGE_SIZE = 100

# Base options for dropdowns
base_status_options = ["Not Started", "On-Track", "At-Risk", "Off-Track", "Completed", "Blocked"]
base_product_options = ["MR Desktop", "MR Online", "Data", "Support", "MR Live"]

# This dictionary stores the final state of changed cells across all pages
changed_data = {}

# --- UI Widget Declarations ---
grid = None
update_button = widgets.Button(description="Apply Updates", button_style="success", icon="check")
status_label = widgets.Label(value="Status: Ready")
pagination_buttons = widgets.HBox()
output_area = widgets.Output(layout={'border': '1px solid black', 'padding': '5px', 'margin_top': '10px'})
debug_output = widgets.Output(layout={'padding': '5px'})
debug_accordion = widgets.Accordion(children=[debug_output], titles=('Debug Log',))
debug_accordion.selected_index = None
main_container = widgets.VBox()

# --- Function Definitions ---

def get_dropdown_options():
    try:
        spark_df = spark.table(TABLE_PATH)
        existing_status = [r["Status"] for r in spark_df.select("Status").distinct().where(F.col("Status").isNotNull()).collect()]
        existing_product = [r["Product"] for r in spark_df.select("Product").distinct().where(F.col("Product").isNotNull()).collect()]
        status_options = sorted(set(base_status_options + existing_status)) + [NULL_SENTINEL]
        product_options = sorted(set(base_product_options + existing_product)) + [NULL_SENTINEL]
        return status_options, product_options
    except Exception as e:
        with output_area: print(f"❌ Error fetching dropdown options: {e}")
        raise

def get_paginated_df(page_number: int, page_size: int):
    offset = (page_number - 1) * page_size
    spark_df = spark.table(TABLE_PATH).orderBy(F.col(KEY_COLUMN))
    pandas_df = spark_df.offset(offset).limit(page_size).toPandas()

    if "start_date" in pandas_df.columns: pandas_df["start_date"] = pd.to_datetime(pandas_df["start_date"], errors="coerce")
    for col in ["Status", "Product"]:
        if col in pandas_df.columns: pandas_df[col] = pandas_df[col].fillna(NULL_SENTINEL)
    return pandas_df

def on_cell_changed(change):
    row_index, col_name, new_value = change['row'], change['column'], change['newValue']
    key_value = grid.data.loc[row_index, KEY_COLUMN]
    
    with output_area: print(f"Change captured: Key={key_value}, Column='{col_name}', New Value='{new_value}'")

    if new_value == NULL_SENTINEL: new_value = None
    if col_name == "start_date" and pd.notna(new_value): new_value = pd.to_datetime(new_value).date()

    if key_value not in changed_data: changed_data[key_value] = {}
    changed_data[key_value][col_name] = new_value
    status_label.value = f"Status: {len(changed_data)} record(s) have pending changes."

def draw_grid(page_number):
    global grid
    with output_area:
        output_area.clear_output(); print(f"Loading page {page_number}...")

    try:
        pandas_df = get_paginated_df(page_number, PAGE_SIZE)
        if pandas_df.empty:
            with output_area: output_area.clear_output(); print("No more data to display.")
            return

        STATUS_OPTIONS, PRODUCT_OPTIONS = get_dropdown_options()
        renderers = {
            col: (ipydatagrid.TextRenderer(read_only=True) if col not in EDITABLE_COLUMNS else
                  ipydatagrid.DropdownRenderer(options=STATUS_OPTIONS) if col == "Status" else
                  ipydatagrid.DropdownRenderer(options=PRODUCT_OPTIONS) if col == "Product" else
                  ipydatagrid.DateRenderer() if col == "start_date" else
                  ipydatagrid.TextRenderer())
            for col in pandas_df.columns
        }
        renderers[KEY_COLUMN] = ipydatagrid.TextRenderer(read_only=True)

        grid = ipydatagrid.DataGrid(dataframe=pandas_df, editable=True, renderers=renderers, layout={"height": "400px"})
        grid.on_cell_changed(on_cell_changed)
        main_container.children = [pagination_buttons, grid, update_button, status_label, output_area, debug_accordion]
        
        with output_area: output_area.clear_output(); status_label.value = "Status: Ready"

    except Exception as e:
        with output_area:
            output_area.clear_output()
            print(f"❌ Failed to load page {page_number}: {e}")
            traceback.print_exc()

def create_pagination_controls():
    total_records = spark.table(TABLE_PATH).count()
    total_pages = (total_records + PAGE_SIZE - 1) // PAGE_SIZE
    current_page = 1

    def go_to_page(page):
        nonlocal current_page
        if 1 <= page <= total_pages:
            current_page = page; draw_grid(current_page)
            page_label.value = "Page {} of {}".format(current_page, total_pages)

    prev_button, next_button = widgets.Button(description="Previous", icon="arrow-left"), widgets.Button(description="Next", icon="arrow-right")
    page_label = widgets.Label("Page {} of {}".format(current_page, total_pages))
    
    prev_button.on_click(lambda b: go_to_page(current_page - 1))
    next_button.on_click(lambda b: go_to_page(current_page + 1))
    return widgets.HBox([prev_button, next_button, page_label])


# --- Main Execution Block for Cell 1 ---
try:
    # Create UI components and display them
    pagination_buttons = create_pagination_controls()
    main_container.children = [pagination_buttons, update_button, status_label, output_area, debug_accordion]
    display(main_container)
    
    # Initial grid render
    draw_grid(1)
except Exception as e:
    with output_area:
        output_area.clear_output()
        print(f"❌ Notebook initialization failed. See details below.")
        traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Cell 2: Update Logic
# MAGIC This cell defines and attaches the logic for the "Apply Updates" button. Run this cell after running Cell 1.

# COMMAND ----------

# This cell defines the logic that runs when the "Apply Updates" button is clicked.
# The button was created and the event handler was attached in the previous cell.

def on_update_button_clicked(_):
    with output_area: output_area.clear_output()
    with debug_output: debug_output.clear_output()

    if not changed_data:
        with output_area: print("ℹ️ No changes detected. Nothing to update.")
        return

    with output_area: print(f"Processing {len(changed_data)} changed record(s)...")

    try:
        # --- Create and Validate Pandas DataFrame ---
        updates_list = [dict(v, **{KEY_COLUMN: k}) for k, v in changed_data.items()]
        updates_pd = pd.DataFrame(updates_list)

        if updates_pd[KEY_COLUMN].isnull().any():
            raise ValueError(f"CRITICAL: One or more edited rows has a null value in the key column '{KEY_COLUMN}'. Cannot proceed.")

        for col in EDITABLE_COLUMNS:
            if col not in updates_pd.columns: updates_pd[col] = pd.NA
        
        with debug_output:
            print("--- [Debug 1/4] Raw Pandas DataFrame from UI changes ---")
            display(updates_pd.head())

        # --- Define Schema and Create Spark DataFrame ---
        merge_schema = StructType([
            StructField(KEY_COLUMN, LongType(), False), StructField("start_date", DateType(), True),
            StructField("Status", StringType(), True), StructField("Callouts", StringType(), True),
            StructField("Product", StringType(), True),
        ])
        
        with debug_output:
            print("\n--- [Debug 2/4] Schema for Spark DataFrame (for MERGE) ---"); print(merge_schema)

        updates_spark_df = spark.createDataFrame(updates_pd, schema=merge_schema)
        
        with debug_output:
            print("\n--- [Debug 3/4] Final Spark DataFrame sample before MERGE ---")
            buf = io.StringIO(); updates_spark_df.show(5, False, output=buf); print(buf.getvalue())

        # --- Perform MERGE ---
        updates_spark_df.createOrReplaceTempView("updates_to_merge")
        spark.sql(f"""
            MERGE INTO {TABLE_PATH} AS target USING updates_to_merge AS source
            ON target.{KEY_COLUMN} = source.{KEY_COLUMN}
            WHEN MATCHED THEN UPDATE SET
                target.start_date = source.start_date, target.Status = source.Status,
                target.Callouts = source.Callouts, target.Product = source.Product
        """)

        dt = DeltaTable.forName(spark, TABLE_PATH)
        op_metrics = dt.history(1).select("operationMetrics").collect()[0][0] or {}
        num_updated = int(op_metrics.get("numTargetRowsUpdated", op_metrics.get("numUpdatedRows", 0)))

        # --- Post-Flight Analysis ---
        if num_updated > 0:
            with output_area:
                print(f"✅ Success! {num_updated} record(s) were updated in {TABLE_PATH}.")
        else:
            with output_area:
                print(f"⚠️ Merge complete, but 0 records were updated. Running diagnosis...")
            
            keys_to_check = [row[KEY_COLUMN] for row in updates_spark_df.select(KEY_COLUMN).collect()]
            target_df = spark.table(TABLE_PATH).where(F.col(KEY_COLUMN).isin(keys_to_check))
            
            with debug_output:
                print(f"\n--- [Debug 4/4] Post-Flight Analysis for Zero Updates ---")
                if target_df.count() == 0:
                    print("DIAGNOSIS: No-Match Failure.")
                    print(f"The key(s) you edited {keys_to_check} were NOT FOUND in the target table '{TABLE_PATH}'.")
                    print("RESOLUTION: Verify that these keys exist in the table. They may have been changed or deleted by another process.")
                else:
                    print("DIAGNOSIS: Data Already Matched.")
                    print("The keys you edited were found, but the data in the table already matches the values you submitted.")
                    print("RESOLUTION: This is expected if you changed a value and then changed it back. No action needed.")
                    print("Current data in table for submitted keys:")
                    target_df.show(truncate=False)

        changed_data.clear()
        status_label.value = "Status: Ready"
        debug_accordion.selected_index = 0

    except Exception as e:
        with output_area:
            print("❌ An error occurred during the update. Check the debug log for the full error.")
            debug_accordion.selected_index = 0
        with debug_output:
            import traceback; traceback.print_exc()

# --- Main Execution Block for Cell 2 ---
# This line attaches the function above to the button that was created in Cell 1.
update_button.on_click(on_update_button_clicked)

print("Update logic has been attached to the 'Apply Updates' button.")
```
