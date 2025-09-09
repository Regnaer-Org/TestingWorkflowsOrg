import pyspark.sql.functions as F
from pyspark.sql.types import *
import pandas as pd
import ipywidgets as widgets
from IPython.display import display

# Configuration
table_path = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"
editable_columns = ["start_date", "Status", "Callouts", "Product"]
key_column = "surrogate_key" # The primary key for merging

# Dropdown options
status_options = ["Not Started", "On-Track", "At-Risk", "Off-Track", "Completed", "Blocked"]
product_options = ["MR Desktop", "MR Online", "Data", "Support", "MR Live"]

# 1. Load the data from the Delta table into a pandas DataFrame
try:
    spark_df = spark.table(table_path)
    pandas_df = spark_df.toPandas()
    print(f"Successfully loaded {len(pandas_df)} records from {table_path}")
except Exception as e:
    print(f"Error loading table: {e}")
    # Stop execution if the table can't be loaded
    dbutils.notebook.exit("Stopping notebook due to data loading error.")

# Create a grid to display the data and allow edits
def create_editable_grid(df):
    
    # Create a widget for each cell in the dataframe
    rows = []
    for i in range(len(df)):
        cols = []
        for col in df.columns:
            if col in editable_columns:
                if col == "Status":
                    widget = widgets.Dropdown(options=status_options, value=df.loc[i, col], layout={'width': '150px'})
                elif col == "Product":
                    widget = widgets.Dropdown(options=product_options, value=df.loc[i, col], layout={'width': '150px'})
                elif col == "start_date":
                     # Assuming the date is in a string format that the DatePicker can handle
                    widget = widgets.DatePicker(value=pd.to_datetime(df.loc[i, col]))
                else: # For 'Callouts' and other text fields
                    widget = widgets.Text(value=str(df.loc[i, col]), layout={'width': '200px'})
            else:
                # For non-editable columns, just display the text
                widget = widgets.Label(value=str(df.loc[i, col]))
            cols.append(widget)
        rows.append(widgets.HBox(cols))

    # Create column headers
    header = widgets.HBox([widgets.Label(value=col, layout={'width': '150px' if col in ["Status", "Product"] else '200px'}) for col in df.columns])
    
    return header, rows

header, grid_rows = create_editable_grid(pandas_df)
grid = widgets.VBox(grid_rows)

# 2. Display the editable table
print("\nEditable Table:")
display(header, grid)

# 3. Create the 'Update' button
update_button = widgets.Button(description="Update Table", button_style='success')
output_area = widgets.Output()

# 4. Define the update logic
def on_update_button_clicked(b):
    with output_area:
        output_area.clear_output()
        print("Starting update process...")

        try:
            # Collect the new values from the widgets
            new_data = []
            for hbox in grid.children:
                row = {}
                for i, col_name in enumerate(pandas_df.columns):
                    widget = hbox.children[i]
                    row[col_name] = widget.value
                new_data.append(row)
            
            updated_pandas_df = pd.DataFrame(new_data)
            
            # Convert pandas DataFrame back to Spark DataFrame
            # Ensure schema matches the original table to avoid conversion errors
            updated_spark_df = spark.createDataFrame(updated_pandas_df, schema=spark_df.schema)

            # 6. Merge the new values into the existing table
            spark.sql(f"""
                MERGE INTO {table_path} AS target
                USING (SELECT * FROM updated_view) AS source
                ON target.{key_column} = source.{key_column}
                WHEN MATCHED THEN
                    UPDATE SET
                        target.start_date = source.start_date,
                        target.Status = source.Status,
                        target.Callouts = source.Callouts,
                        target.Product = source.Product
            """)

            # Use a temporary view for the merge operation
            updated_spark_df.createOrReplaceTempView("updated_view")

            # Execute the merge
            merge_result = spark.sql(f"""
                MERGE INTO {table_path} AS target
                USING updated_view AS source
                ON target.{key_column} = source.{key_column}
                WHEN MATCHED THEN
                  UPDATE SET *
            """)
            
            # The result of a MERGE operation is a DataFrame with metrics.
            # We can extract the number of updated rows from it.
            result_metrics = merge_result.select(F.sum("num_updated_rows").alias("total_updated")).first()
            num_updated = result_metrics['total_updated'] if result_metrics and 'total_updated' in result_metrics else 0


            # 7. Success message
            print(f"✅ Success! {num_updated} records were updated in {table_path}.")

        except Exception as e:
            print(f"❌ An error occurred during the update: {e}")
            # Consider more detailed error logging for debugging if needed
            import traceback
            traceback.print_exc()

# Link the button to the update function
update_button.on_click(on_update_button_clicked)

# Display the button and the output area
display(update_button, output_area)
