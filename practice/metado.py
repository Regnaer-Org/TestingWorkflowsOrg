# Databricks notebook to ingest Azure DevOps work items into a Delta table
# Version 3: Implements more explicit Authorization header for robustness in SSO/proxy environments.

import requests
import json
import base64
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, BooleanType, TimestampType

# --------------------------------------------------------------------------
# 1. Configuration
# --------------------------------------------------------------------------
# Azure DevOps Organization URL
ado_organization_url = "https://guycarp.visualstudio.com"

# List of Azure DevOps projects to query
ado_projects = [
    "CAT Modernization",
    "Sunstone",
    "EventBuilder",
    "AdvantagePoint"
]

# Databricks secret scope and key for the Azure DevOps PAT
databricks_secret_scope = "gap_agile"
databricks_secret_key = "ado_ingestion_gap"

# Target Databricks table details
target_catalog = "gc_prod_sandbox"
target_schema = "su_eric_regna"
target_table_name = "ado_milestones_dim"
full_table_name = f"{target_catalog}.{target_schema}.{target_table_name}"

# Fields to retrieve from Azure DevOps work items
fields_to_return = {
    "AreaPath": "System.AreaPath",
    "AssignedTo": "System.AssignedTo",
    "Announceable": "Custom.Announceable",
    "BusinessAnnounceable": "Custom.BusinessAnnounceable",
    "Overdue": "Custom.Overdue",
    "OriginalTargetDate": "Custom.OriginalTargetDate",
    "ProductionDeployment": "Custom.ProductionDeployment",
    "ActionOwner": "Custom.ActionOwner",
    "IterationPath": "System.IterationPath",
    "Description": "System.Description",
    "Reason": "System.Reason",
    "State": "System.State",
    "Tags": "System.Tags",
    "TargetDate": "Microsoft.VSTS.Scheduling.TargetDate",
    "Title": "System.Title",
    "WorkItemID": "System.Id",
    "WorkItemType": "System.WorkItemType"
}

# API Version for Azure DevOps
api_version = "7.1-preview.3"

# --------------------------------------------------------------------------
# 2. Authentication and Initialization
# --------------------------------------------------------------------------
# Retrieve the Personal Access Token (PAT) from Databricks secrets
try:
    personal_access_token = dbutils.secrets.get(scope=databricks_secret_scope, key=databricks_secret_key)
except Exception as e:
    print(f"Error retrieving secret: {e}")
    dbutils.notebook.exit("Failed to retrieve ADO PAT from Databricks secrets. Please check scope and key names.")

# --- NEW: Explicit Authorization Header Construction ---
# Manually create the Basic Authentication header. This is often more reliable in corporate proxy environments.
# The format is "Basic " followed by a base64 encoding of ":<PAT>".
auth_string = f":{personal_access_token}"
encoded_auth_string = base64.b64encode(auth_string.encode('ascii')).decode('ascii')

headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Basic {encoded_auth_string}'
}

# Initialize Spark Session
spark = SparkSession.builder.appName("AzureDevOpsIngestion").getOrCreate()

print("Configuration and authentication complete. Using explicit Authorization header.")

# --------------------------------------------------------------------------
# 3. Fetch Work Item IDs using WIQL (Work Item Query Language)
# --------------------------------------------------------------------------
all_work_item_ids = []

for project in ado_projects:
    print(f"Fetching work item IDs for project: '{project}'...")

    wiql_query = {
        "query": f"""
            SELECT [System.Id]
            FROM WorkItems
            WHERE [System.TeamProject] = @project
            AND [System.WorkItemType] = 'Milestone'
            AND [System.AreaPath] UNDER '{project}'
        """
    }
    wiql_url = f"{ado_organization_url}/{project}/_apis/wit/wiql?api-version=7.1-preview.2"
    
    # Make the API call using the manually constructed headers, REMOVING the 'auth' parameter.
    response = requests.post(wiql_url, headers=headers, data=json.dumps(wiql_query))

    if response.status_code == 200:
        results = response.json()
        work_items = results.get('workItems', [])
        project_ids = [item['id'] for item in work_items]
        all_work_item_ids.extend(project_ids)
        print(f"  Found {len(project_ids)} 'Milestone' work items in '{project}'.")
    else:
        # Provide more detailed error info
        print(f"  ERROR fetching work items for project '{project}'. Status Code: {response.status_code}")
        print(f"  Response Headers: {response.headers}")
        print(f"  Response Body: {response.text}")

print(f"\nTotal 'Milestone' work item IDs found across all projects: {len(all_work_item_ids)}")

# --------------------------------------------------------------------------
# 4. Fetch Detailed Information for each Work Item
# --------------------------------------------------------------------------
work_item_details_list = []

if all_work_item_ids:
    field_list_for_api = ",".join(fields_to_return.values())
    
    batch_size = 200
    for i in range(0, len(all_work_item_ids), batch_size):
        batch_ids = all_work_item_ids[i:i + batch_size]
        print(f"Fetching details for batch {i//batch_size + 1}...")

        work_items_url = f"{ado_organization_url}/_apis/wit/workitems?ids={','.join(map(str, batch_ids))}&fields={field_list_for_api}&api-version={api_version}"
        
        # Make the API call using the manually constructed headers, REMOVING the 'auth' parameter.
        response = requests.get(work_items_url, headers=headers)

        if response.status_code == 200:
            work_item_details_list.extend(response.json().get('value', []))
        else:
            print(f"  ERROR fetching work item details for batch. Status Code: {response.status_code}")
            print(f"  Response Headers: {response.headers}")
            print(f"  Response Body: {response.text}")

print(f"\nTotal work item details retrieved: {len(work_item_details_list)}")


# --------------------------------------------------------------------------
# 5. Process Data and Create Spark DataFrame (Logic remains the same)
# --------------------------------------------------------------------------
if work_item_details_list:
    processed_rows = []
    missing_fields_tracker = set()

    print("\nProcessing work item details and checking for missing fields...")
    for item in work_item_details_list:
        work_item_id = item.get('id')
        api_fields = item.get('fields', {})
        
        if not api_fields:
            print(f"  WARNING: Work item {work_item_id} has no 'fields' attribute. Skipping.")
            continue
            
        row = {}
        row['WorkItemID'] = work_item_id
        
        for friendly_name, api_name in fields_to_return.items():
            if api_name not in api_fields:
                if api_name not in missing_fields_tracker:
                    print(f"  WARNING: Field '{friendly_name}' (API name: '{api_name}') not found in response. It will be null. This message will not be repeated.")
                    missing_fields_tracker.add(api_name)
                row[friendly_name] = None
                continue

            value = api_fields.get(api_name)

            if (friendly_name == 'AssignedTo' or friendly_name == 'ActionOwner') and value:
                if isinstance(value, dict) and 'displayName' in value:
                    row[friendly_name] = value['displayName']
                else:
                    if friendly_name not in missing_fields_tracker:
                         print(f"  WARNING: Field '{friendly_name}' for work item {work_item_id} was not a dictionary with 'displayName'. Value: {value}. This message will not be repeated.")
                         missing_fields_tracker.add(friendly_name)
                    row[friendly_name] = None
            else:
                row[friendly_name] = value

        processed_rows.append(row)

    if missing_fields_tracker:
        print("\nNOTE: One or more fields were not found in the API response. Please verify the custom field names in your Azure DevOps project process settings.")

    schema = StructType([
        StructField("WorkItemID", IntegerType(), True),
        StructField("AreaPath", StringType(), True),
        StructField("AssignedTo", StringType(), True),
        StructField("Announceable", BooleanType(), True),
        StructField("BusinessAnnounceable", BooleanType(), True),
        StructField("Overdue", BooleanType(), True),
        StructField("OriginalTargetDate", TimestampType(), True),
        StructField("ProductionDeployment", TimestampType(), True),
        StructField("ActionOwner", StringType(), True),
        StructField("IterationPath", StringType(), True),
        StructField("Description", StringType(), True),
        StructField("Reason", StringType(), True),
        StructField("State", StringType(), True),
        StructField("Tags", StringType(), True),
        StructField("TargetDate", TimestampType(), True),
        StructField("Title", StringType(), True),
        StructField("WorkItemType", StringType(), True),
    ])

    final_df = spark.createDataFrame(processed_rows, schema)
    
    print("\nDataFrame created successfully. Schema:")
    final_df.printSchema()
    
    # --------------------------------------------------------------------------
    # 6. Write DataFrame to Delta Table (Logic remains the same)
    # --------------------------------------------------------------------------
    print(f"\nWriting data to Delta table: {full_table_name}")

    (final_df.write
        .format("delta")
        .mode("overwrite")
        .option("mergeSchema", "true")
        .saveAsTable(full_table_name))

    print("Data ingestion complete.")
    
    print("\nSample of the ingested data:")
    spark.table(full_table_name).show(10, truncate=False)

else:
    print("\nNo work items found to process. The target table was not created or updated.")
