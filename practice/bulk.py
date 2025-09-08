# Databricks notebook source
# Title: Bulk Edit UI for gc_prod_sandbox.su_eric_regna.metarisk_releases_dim
#
# What this does
# - Displays a business-friendly editable table (Streamlit data editor).
# - Only editable columns can be changed: start_date, Status, Callouts, Product.
# - On "Update", merges changes into the target Delta table using surrogate_key as the stable identifier.
# - Prints a success message with how many records were updated.
#
# Why this approach
# - Uses Streamlit's st.data_editor (simple, robust), with dropdowns for Status/Product.
# - Diff original vs. edited rows to produce a minimal set of updates.
# - Convert UI changes into a Spark DataFrame and MERGE into the table.
# - Light-touch validation and error handling for reliability without added complexity.
#
# Notes
# - You must have SELECT and UPDATE privileges on the target table.
# - Best run as a Databricks "Streamlit" app or directly in a Notebook that supports Streamlit.
# - References for best-practice patterns: Databricks Apps with Streamlit data editor and Delta write-back.

# COMMAND ----------

# If streamlit is not available in your environment, uncomment the following line:
# %pip install streamlit

# COMMAND ----------

import datetime
import typing as t

import pandas as pd
import pyspark.sql.functions as F
import pyspark.sql.types as T
from pyspark.sql import SparkSession

import streamlit as st

spark: SparkSession = spark  # provided by Databricks runtime

# --- Configuration ---
TABLE = "gc_prod_sandbox.su_eric_regna.metarisk_releases_dim"

# UI editable columns (user-facing names)
UI_EDITABLE_COLS = ["start_date", "Status", "Callouts", "Product"]

# Mapping between UI column names and physical table column names
UI_TO_PHYSICAL = {
    "Status": "state",
    "Callouts": "Callouts",
    "start_date": "start_date",
    "Product": "Product",
}
PHYSICAL_TO_UI = {v: k for k, v in UI_TO_PHYSICAL.items()}

# Dropdown options (include a blank option "" to allow clearing the value)
STATUS_OPTIONS = ["", "Not Started", "On-Track", "At-Risk", "Off-Track", "Completed", "Blocked"]
PRODUCT_OPTIONS = ["", "MR Desktop", "MR Online", "Data", "Support", "MR Live"]

# --- UI Header ---
st.title("Bulk Edit: metarisk_releases_dim")
st.caption("Edit only the allowed fields, then click Update to apply changes via MERGE.")

with st.expander("Target table", expanded=False):
    st.code(TABLE)

# COMMAND ----------

@st.cache_data(show_spinner=False)
def load_table_for_edit() -> pd.DataFrame:
    """
    Load the table and return a pandas DataFrame with key + editable columns (UI naming).
    Uses surrogate_key as immutable row identifier for MERGE.
    """
    df = spark.table(TABLE)

    required_cols = ["surrogate_key", "start_date", "state", "Callouts", "Product"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in table: {missing}")

    sdf = df.select("surrogate_key", "start_date", "state", "Callouts", "Product")
    pdf = sdf.toPandas()

    # Rename for UI presentation
    pdf = pdf.rename(columns={"state": "Status"})

    # Sort for stable display
    pdf = pdf.sort_values(by="surrogate_key").reset_index(drop=True)
    return pdf


def coerce_to_date(x: t.Any) -> t.Optional[datetime.date]:
    """
    Convert various input types to a Python date or None.
    """
    if x is None or (isinstance(x, float) and pd.isna(x)) or (isinstance(x, str) and x.strip() == ""):
        return None
    if isinstance(x, datetime.date) and not isinstance(x, datetime.datetime):
        return x
    if isinstance(x, (pd.Timestamp, datetime.datetime)):
        return x.date()
    if isinstance(x, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(x, fmt).date()
            except ValueError:
                pass
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return None
    return None


def diff_changes(original_ui: pd.DataFrame, edited_ui: pd.DataFrame) -> pd.DataFrame:
    """
    Compute rows with any changes in editable columns.
    Returns a DataFrame containing changed rows with columns: surrogate_key + UI editable columns (normalized).
    """
    orig = original_ui.set_index("surrogate_key")
    edited = edited_ui.set_index("surrogate_key")

    ecols = [c for c in UI_EDITABLE_COLS if c in orig.columns and c in edited.columns]

    def norm(col: pd.Series) -> pd.Series:
        if col.name == "start_date":
            return col.map(coerce_to_date)
        # Normalize empties to None for fair comparison
        return col.map(lambda v: None if (isinstance(v, str) and v.strip() == "") else v)

    orig_norm = orig[ecols].apply(norm)
    edited_norm = edited[ecols].apply(norm)

    changed_mask = (orig_norm != edited_norm).any(axis=1)
    changed = edited_norm[changed_mask].reset_index()
    return changed


def validate_changed_rows(changed_ui_rows: pd.DataFrame) -> list[str]:
    """
    Validate only the changed rows for dropdown values and date parseability.
    """
    errors: list[str] = []

    if changed_ui_rows.empty:
        return errors

    # Validate Status/Product against allowed lists (excluding blank is allowed via "")
    if "Status" in changed_ui_rows.columns:
        invalid = sorted(
            set(v for v in changed_ui_rows["Status"].dropna().tolist() if v not in STATUS_OPTIONS)
        )
        if invalid:
            errors.append(f"Invalid Status values: {invalid}. Allowed: {STATUS_OPTIONS}")

    if "Product" in changed_ui_rows.columns:
        invalid = sorted(
            set(v for v in changed_ui_rows["Product"].dropna().tolist() if v not in PRODUCT_OPTIONS)
        )
        if invalid:
            errors.append(f"Invalid Product values: {invalid}. Allowed: {PRODUCT_OPTIONS}")

    # Validate start_date parseability
    if "start_date" in changed_ui_rows.columns:
        unparsable_idx = []
        for i, v in changed_ui_rows["start_date"].items():
            if coerce_to_date(v) is None and not (v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() == "")):
                unparsable_idx.append(i)
        if unparsable_idx:
            errors.append(f"Unparsable start_date at rows (0-based): {unparsable_idx}. Use formats like YYYY-MM-DD.")

    return errors


def to_updates_spark_df(changed_ui_rows: pd.DataFrame):
    """
    Convert changed UI rows into a Spark DataFrame with physical column names and proper types for MERGE.
    """
    if changed_ui_rows.empty:
        return spark.createDataFrame([], schema=T.StructType([
            T.StructField("surrogate_key", T.LongType(), False),
            T.StructField("start_date", T.DateType(), True),
            T.StructField("state", T.StringType(), True),
            T.StructField("Callouts", T.StringType(), True),
            T.StructField("Product", T.StringType(), True),
        ]))

    # Rename UI -> physical
    pdf = changed_ui_rows.rename(columns=UI_TO_PHYSICAL).copy()

    # Coerce types and normalize blank strings to None
    if "start_date" in pdf.columns:
        pdf["start_date"] = pdf["start_date"].map(coerce_to_date)

    for c in ["state", "Callouts", "Product"]:
        if c not in pdf.columns:
            pdf[c] = None
        else:
            pdf[c] = pdf[c].map(lambda v: None if (isinstance(v, str) and v.strip() == "") else v)

    # Ensure required columns and order
    pdf = pdf[["surrogate_key", "start_date", "state", "Callouts", "Product"]]

    schema = T.StructType([
        T.StructField("surrogate_key", T.LongType(), False),
        T.StructField("start_date", T.DateType(), True),
        T.StructField("state", T.StringType(), True),
        T.StructField("Callouts", T.StringType(), True),
        T.StructField("Product", T.StringType(), True),
    ])
    return spark.createDataFrame(pdf, schema=schema)

# COMMAND ----------

# Load data
try:
    original_ui_df = load_table_for_edit()
except Exception as e:
    st.error(f"Failed to load table {TABLE}: {e}")
    st.stop()

# COMMAND ----------

st.subheader("Edit rows (only editable columns are enabled)")

# Working dataframe: key + editable columns
ui_df = original_ui_df[["surrogate_key"] + UI_EDITABLE_COLS].copy()

# Column configuration for Streamlit data editor
col_config = {
    "surrogate_key": st.column_config.NumberColumn(
        "surrogate_key", help="Immutable row identifier (used for MERGE).", disabled=True, format="%d"
    ),
    "start_date": st.column_config.DateColumn(
        "start_date", help="Editable. Release start date (YYYY-MM-DD)."
    ),
    "Status": st.column_config.SelectboxColumn(
        "Status", options=STATUS_OPTIONS, help="Editable. Status of the release."
    ),
    "Callouts": st.column_config.TextColumn(
        "Callouts", help="Editable. Free-form notes."
    ),
    "Product": st.column_config.SelectboxColumn(
        "Product", options=PRODUCT_OPTIONS, help="Editable. Product line."
    ),
}

edited_ui_df = st.data_editor(
    ui_df,
    hide_index=True,
    column_order=["surrogate_key"] + UI_EDITABLE_COLS,
    column_config=col_config,
    use_container_width=True,
    num_rows="fixed",  # prevent adding/removing rows
)

# COMMAND ----------

st.divider()
if st.button("Update", type="primary"):
    try:
        # Compute changed rows first (so we only validate what's changed)
        changed_rows = diff_changes(ui_df, edited_ui_df)

        if changed_rows.empty:
            st.info("No changes detected. Nothing to update.")
            st.stop()

        # Validate only the changed rows
        validation_errors = validate_changed_rows(changed_rows)
        if validation_errors:
            for msg in validation_errors:
                st.error(msg)
            st.stop()

        st.write(f"Detected {len(changed_rows)} edited row(s). Preparing update...")

        # Convert to Spark DF for MERGE
        updates_sdf = to_updates_spark_df(changed_rows)
        updates_sdf.createOrReplaceTempView("updates_to_merge")

        # Count how many target rows will be matched by key
        match_count = spark.sql(f"""
            SELECT COUNT(DISTINCT t.surrogate_key) AS cnt
            FROM {TABLE} t
            INNER JOIN (SELECT DISTINCT surrogate_key FROM updates_to_merge) u
            ON t.surrogate_key = u.surrogate_key
        """).collect()[0]["cnt"]

        if match_count == 0:
            st.error("No matching surrogate_key values found in target table. Aborting.")
            st.stop()

        # Perform MERGE (set only the editable fields)
        spark.sql(f"""
            MERGE INTO {TABLE} AS t
            USING updates_to_merge AS s
            ON t.surrogate_key = s.surrogate_key
            WHEN MATCHED THEN UPDATE SET
              t.start_date = s.start_date,
              t.state      = s.state,
              t.Callouts   = s.Callouts,
              t.Product    = s.Product
        """)

        # Clear cache so subsequent loads reflect updates
        st.cache_data.clear()
        st.success(f"Update complete. {match_count} row(s) updated in {TABLE}.")

    except Exception as e:
        st.error(f"Update failed: {e}")
        st.stop()

# COMMAND ----------

with st.expander("Preview (read-only) of current table after updates", expanded=False):
    try:
        preview_pdf = spark.table(TABLE).limit(1000).toPandas()
        st.dataframe(preview_pdf, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"Could not load preview: {e}")
