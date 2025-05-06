1| import os
2| import requests
3| import json
4| import csv
5| from datetime import datetime, timedelta, timezone
6| import sys
7| import time
8| 
9| # --- Configuration ---\n10| PROJECT_ID = os.environ.get("PROJECT_ID", "PVT_kwDODH0FwM4A3yi4") # Get from env var or use default
11| GRAPHQL_API_URL = "https://api.github.com/graphql"
12| OUTPUT_DIR = "agilereporting"
13| TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")
14| 
15| if not TOKEN:
16|     print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
17|     sys.exit(1)
18| if not PROJECT_ID:
19|     print("Error: PROJECT_ID environment variable not set.", file=sys.stderr)
20|     sys.exit(1)
21| 
22| # --- Generate Filename (Central Time, YYYY.MM.DD) ---\n23| utc_now = datetime.now(timezone.utc)
24| try:
25|     # Use zoneinfo if available (Python 3.9+) for better timezone handling
26|     from zoneinfo import ZoneInfo
27|     chicago_tz = ZoneInfo("America/Chicago")
28|     chicago_now = utc_now.astimezone(chicago_tz)
29|     snapshot_date = chicago_now.strftime('%Y.%m.%d')
30| except ImportError:
31|     # Fallback for older Python versions (less accurate DST handling)
32|     print("Warning: zoneinfo module not found. Approximating Chicago time offset.", file=sys.stderr)
33|     chicago_offset = timedelta(hours=-5) # Manual offset (CDT approximation)
34|     chicago_now = utc_now + chicago_offset
35|     snapshot_date = chicago_now.strftime('%Y.%m.%d')
36| except Exception as e:
37|      # General fallback if timezone lookup fails
38|      print(f"Warning: Could not determine Chicago time precisely ({e}). Using UTC date.", file=sys.stderr)
39|      snapshot_date = utc_now.strftime('%Y.%m.%d')
40| 
41| SNAPSHOT_FILENAME = f"project.issues_{snapshot_date}.csv"
42| OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)
43| # Define the new static filename for the latest snapshot
44| LATEST_SNAPSHOT_FILENAME = "latest_snapshot.csv"
45| LATEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, LATEST_SNAPSHOT_FILENAME)
46| 
47| # --- GraphQL Query (Includes labels, assignees nodes) ---\n48| graphql_query = """
49| query GetProjectV2Items($projectId: ID!, $cursor: String) {
50|   node(id: $projectId) {
51|     ... on ProjectV2 {
52|       id
53|       title
54|       number
55|       items(first: 100, after: $cursor, orderBy: {field: POSITION, direction: ASC}) {
56|         totalCount
57|         nodes {
58|           id # ProjectV2 Item ID
59|           createdAt
60|           updatedAt
61|           isArchived
62|           type # ISSUE, PULL_REQUEST, DRAFT_ISSUE
63|           fieldValues(first: 100) { # Get all custom fields for the item
64|             nodes {
65|               ... on ProjectV2ItemFieldTextValue {
66|                 text
67|                 field { ...ProjectV2FieldCommon }
68|               }
69|               ... on ProjectV2ItemFieldDateValue {
70|                 date
71|                 field { ...ProjectV2FieldCommon }
72|               }
73|               ... on ProjectV2ItemFieldNumberValue {
74|                 number
75|                 field { ...ProjectV2FieldCommon }
76|               }
77|               ... on ProjectV2ItemFieldSingleSelectValue {
78|                 name # Option selected
79|                 field { ...ProjectV2FieldCommon }
80|               }
81|               ... on ProjectV2ItemFieldIterationValue {
82|                 title # Iteration title
83|                 startDate
84|                 duration
85|                 field { ...ProjectV2FieldCommon }
86|               }
87|               # Add fragments for other field types if needed
88|             }
89|           }
90|           content {
91|             ... on DraftIssue {
92|               id
93|               title
94|               body
95|               creator { login }
96|             }
97|             ... on PullRequest {
98|               id
99|               number
100|               title
101|               state # OPEN, CLOSED, MERGED
102|               url
103|               createdAt
104|               updatedAt
105|               closedAt
106|               mergedAt
107|               author { login }
108|               repository { nameWithOwner owner { login } name }
109|               assignees(first: 10) { nodes { login } } # Request assignees
110|               labels(first: 20) { nodes { name } }     # Request labels
111|               milestone { title number state }
112|             }
113|             ... on Issue {
114|               id
115|               number
116|               title
117|               state # OPEN, CLOSED
118|               url
119|               createdAt
120|               updatedAt
121|               closedAt
122|               author { login }
123|               repository { nameWithOwner owner { login } name }
124|               assignees(first: 10) { nodes { login } } # Request assignees
125|               labels(first: 20) { nodes { name } }     # Request labels
126|               milestone { title number state }
127|             }
128|           }
129|         }
130|         pageInfo {
131|           endCursor
132|           hasNextPage
133|         }
134|       }
135|     }
136|   }
137| }
138| 
139| fragment ProjectV2FieldCommon on ProjectV2FieldCommon {
140|     ... on ProjectV2Field { name id }
141|     ... on ProjectV2IterationField { name id }
142|     ... on ProjectV2SingleSelectField { name id }
143|     # Add other field types here if you add fragments for them above
144| }
145| """
146| 
147| # --- Helper Function to Safely Get Nested Values (for single values) ---\n148| def get_value(data, keys, default=""):
149|     """Safely retrieve nested dictionary values."""
150|     current = data
151|     for key in keys:
152|         if isinstance(current, dict):
153|             current = current.get(key)
154|         else: # Not a dictionary, cannot proceed
155|             return default
156|         if current is None: # Key not found or value is None
157|             return default
158|     # Convert final result to string for CSV consistency
159|     return str(current) if current is not None else default
160| 
161| # --- Fetch All Items via Pagination ---\n162| all_items = []
163| has_next_page = True
164| cursor = None
165| item_count = 0
166| print(f"Fetching items for Project ID: {PROJECT_ID}...")
167| 
168| while has_next_page:
169|     variables = {"projectId": PROJECT_ID, "cursor": cursor}
170|     payload = {"query": graphql_query, "variables": variables}
171|     headers = {
172|         "Authorization": f"Bearer {TOKEN}",
173|         "Content-Type": "application/json",
174|         "Accept": "application/json",
175|     }
176| 
177|     try:
178|         response = requests.post(GRAPHQL_API_URL, headers=headers, json=payload, timeout=60)
179|         response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
180|         data = response.json()
181| 
182|         # Check for GraphQL errors in the response body
183|         if 'errors' in data:
184|             print("Error: GraphQL API returned errors:", file=sys.stderr)
185|             print(json.dumps(data['errors'], indent=2), file=sys.stderr)
186|             # Attempt to process partial data if available, but exit if node is missing
187|             project_data = data.get('data', {}).get('node', {})
188|             if not project_data:
189|                  print("Error: No project data node found in response with errors.", file=sys.stderr)
190|                  sys.exit(1)
191|         else: # No GraphQL errors
192|              project_data = data.get('data', {}).get('node', {})
193| 
194|         # Ensure project data node exists
195|         if not project_data:
196|             print("Error: Could not find project node in response.", file=sys.stderr)
197|             print(json.dumps(data, indent=2), file=sys.stderr) # Print full response for debug
198|             sys.exit(1)
199| 
200|         # Extract items data
201|         items_data = project_data.get('items', {})
202|         nodes = items_data.get('nodes', [])
203|         page_info = items_data.get('pageInfo', {})
204| 
205|         if nodes:
206|             all_items.extend(nodes)
207|             item_count += len(nodes)
208|             total_project_items = items_data.get('totalCount', item_count) # Get total if available
209|             print(f"Fetched {len(nodes)} items (Total processed: {item_count} / {total_project_items or 'unknown'})...")
210| 
211|         # Update pagination info
212|         has_next_page = page_info.get('hasNextPage', False)
213|         cursor = page_info.get('endCursor')
214| 
215|         # Optional delay to avoid secondary rate limits
216|         if has_next_page:
217|              time.sleep(0.2)
218| 
219|     except requests.exceptions.Timeout:
220|         print(f"Error: Request timed out connecting to {GRAPHQL_API_URL}", file=sys.stderr)
221|         sys.exit(1)
222|     except requests.exceptions.RequestException as e:
223|         print(f"Error fetching data from GraphQL API: {e}", file=sys.stderr)
224|         if 'response' in locals() and response is not None:
225|              print(f"Response status code: {response.status_code}", file=sys.stderr)
226|              print(f"Response body: {response.text}", file=sys.stderr)
227|         sys.exit(1)
228|     except json.JSONDecodeError as e:
229|         print(f"Error decoding JSON response: {e}", file=sys.stderr)
230|         if 'response' in locals() and response is not None:
231|              print(f"Response status code: {response.status_code}", file=sys.stderr)
232|              print(f"Response body (first 500 chars): {response.text[:500]}", file=sys.stderr)
233|         sys.exit(1)
234|     except Exception as e:
235|         print(f"An unexpected error occurred during fetching: {e}", file=sys.stderr)
236|         import traceback
237|         traceback.print_exc(file=sys.stderr)
238|         sys.exit(1)
239| 
240| print(f"Finished fetching. Total items retrieved: {len(all_items)}")
241| 
242| # --- Process Data and Prepare for CSV ---\n243| processed_data = []
244| all_field_names = set() # To dynamically collect all ProjectV2 field names
245| 
246| # Define core fields we always expect (order matters for initial set)\n247| core_headers = [
248|     'project_item_id', 'project_item_type', 'project_item_created_at', 'project_item_updated_at', 'project_item_is_archived',
249|     'content_id', 'content_type', 'content_number', 'content_title', 'content_state', 'content_url',
250|     'content_created_at', 'content_updated_at', 'content_closed_at', 'content_merged_at',
251|     'author', 'repository', 'repository_owner', 'repository_name',
252|     'assignees', 'labels',
253|     'milestone_title', 'milestone_number', 'milestone_state'
254| ]
255| # Add core headers to the dynamic set
256| for header in core_headers:
257|      all_field_names.add(header)
258| 
259| 
260| print("Processing items for CSV conversion...")
261| for item in all_items:
262|     row = {} # Initialize row dictionary for this item
263| 
264|     # --- Project Item Core Fields ---\n265|     row['project_item_id'] = item.get('id', '')
266|     row['project_item_type'] = item.get('type', '')
267|     row['project_item_created_at'] = item.get('createdAt', '')
268|     row['project_item_updated_at'] = item.get('updatedAt', '')
269|     row['project_item_is_archived'] = str(item.get('isArchived', '')) # Ensure string
270| 
271|     # --- Content Fields (Issue, PR, DraftIssue) ---\n272|     content = item.get('content')
273|     if content:
274|         # Determine content type
275|         if 'repository' in content: # Issue or PR
276|              if 'mergedAt' in content or content.get('state') == 'MERGED':
277|                   row['content_type'] = 'PullRequest'
278|              else:
279|                   row['content_type'] = 'Issue'
280|         elif 'body' in content and ('creator' in content or 'author' in content): # DraftIssue might use 'author' now
281|             row['content_type'] = 'DraftIssue'
282|         else:
283|             row['content_type'] = 'Unknown' # Should not happen often
284| 
285|         # Basic content fields (using get_value where appropriate for single values)\n286|         row['content_id'] = content.get('id', '') # Direct get is fine
287|         row['content_number'] = str(content.get('number', '')) # Direct get, ensure string
288|         row['content_title'] = content.get('title', '') # Direct get
289|         row['content_state'] = content.get('state', '') # Direct get
290|         row['content_url'] = content.get('url', '') # Direct get
291|         row['content_created_at'] = content.get('createdAt', '') # Direct get
292|         row['content_updated_at'] = content.get('updatedAt', '') # Direct get
293|         row['content_closed_at'] = content.get('closedAt', '') # Direct get
294|         row['content_merged_at'] = content.get('mergedAt', '') # Direct get
295|         row['author'] = get_value(content, ['author', 'login'], get_value(content, ['creator', 'login'])) # Use helper for nested optional author/creator
296|         row['repository'] = get_value(content, ['repository', 'nameWithOwner']) # Use helper
297|         row['repository_owner'] = get_value(content, ['repository', 'owner', 'login']) # Use helper
298|         row['repository_name'] = get_value(content, ['repository', 'name']) # Use helper
299| 
300|         # --- Assignees (Corrected - Direct Access for List) ---\n301|         assignees_nodes = content.get('assignees', {}).get('nodes', [])
302|         if isinstance(assignees_nodes, list):
303|              assignees_logins = [a.get('login', '') for a in assignees_nodes if a and isinstance(a, dict)]
304|              row['assignees'] = ";".join(filter(None, assignees_logins))
305|         else:
306|              row['assignees'] = "" # Default to empty if structure is unexpected
307| 
308|         # --- Labels (Corrected - Direct Access for List) ---\n309|         labels_nodes = content.get('labels', {}).get('nodes', [])
310|         if isinstance(labels_nodes, list):
311|             label_names = [lbl.get('name', '') for lbl in labels_nodes if lbl and isinstance(lbl, dict)]
312|             row['labels'] = ";".join(filter(None, label_names))
313|         else:
314|             row['labels'] = "" # Default to empty if structure is unexpected
315| 
316|         # --- Milestone (using get_value for single nested fields) ---\n317|         row['milestone_title'] = get_value(content, ['milestone', 'title'])
318|         row['milestone_number'] = str(get_value(content, ['milestone', 'number'])) # Ensure string
319|         row['milestone_state'] = get_value(content, ['milestone', 'state'])
320| 
321|     else: # Item might be archived or have no linked content
322|          row['content_type'] = 'No Content'
323|          # Set default empty values for content-related core fields
324|          for key in core_headers:
325|               if key.startswith('content_') or key in ['author','repository','repository_owner','repository_name','assignees','labels','milestone_title','milestone_number','milestone_state']:
326|                    row[key] = ''
327| 
328|     # --- ProjectV2 Custom Fields ---\n329|     field_values = item.get('fieldValues', {}).get('nodes', [])
330|     custom_fields_processed_this_item = set() # Track fields processed for this item
331| 
332|     for fv in field_values:
333|         if not fv or not fv.get('field'): continue # Skip empty/invalid field values
334| 
335|         field_name = fv['field'].get('name')
336|         if not field_name: continue # Skip if field name is missing
337| 
338|         # Sanitize field name for CSV header
339|         sanitized_name = ''.join(c if c.isalnum() else '_' for c in field_name.lower())
340|         header_name = '_'.join(filter(None, sanitized_name.split('_'))) # Collapse underscores
341| 
342|         if not header_name: continue # Skip if sanitized name is empty
343| 
344|         all_field_names.add(header_name) # Add to our dynamic set of all headers
345|         custom_fields_processed_this_item.add(header_name) # Mark as processed for this specific item
346| 
347|         # Extract the value based on type
348|         value = None # Initialize value
349|         if 'text' in fv: value = fv['text']
350|         elif 'number' in fv: value = fv['number']
351|         elif 'date' in fv: value = fv['date']
352|         elif 'name' in fv: value = fv['name'] # SingleSelect option name
353|         elif 'title' in fv: value = fv['title'] # Iteration title
354|         # Add other types like User, Labels if needed in the GraphQL query and here
355| 
356|         # Store the extracted value in the row dictionary, ensure string
357|         row[header_name] = str(value) if value is not None else ''
358| 
359|     # Ensure all dynamically found custom fields exist in the row dictionary for DictWriter
360|     # This step might be redundant if restval='' is used in DictWriter, but can be explicit
361|     # for dynamic_header in all_field_names:
362|     #     if dynamic_header not in core_headers and dynamic_header not in row:
363|     #          row[dynamic_header] = '' # Set default empty for fields not present on this item
364| 
365| 
366|     processed_data.append(row)
367| 
368| # --- Write CSV File Function ---\n369| def write_csv(file_path, data_to_write, headers_list):
370|     print(f"Writing {len(data_to_write)} processed items to {file_path}...")
371|     try:
372|         os.makedirs(OUTPUT_DIR, exist_ok=True) # Ensure output directory exists
373|         with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
374|             writer = csv.DictWriter(csvfile, fieldnames=headers_list, restval='', extrasaction='ignore')
375|             writer.writeheader()
376|             writer.writerows(data_to_write)
377|         print(f"CSV file '{file_path}' written successfully.")
378|     except IOError as e:
379|         print(f"Error writing CSV file '{file_path}': {e}", file=sys.stderr)
380|         sys.exit(1) # Consider if you want to exit for one file failing or just log
381|     except Exception as e:
382|         print(f"An unexpected error occurred during CSV writing for '{file_path}': {e}", file=sys.stderr)
383|         import traceback
384|         traceback.print_exc(file=sys.stderr)
385|         sys.exit(1) # Consider if you want to exit
386| 
387| # --- Prepare final headers and write both CSV files ---\n388| print(f"Preparing to write CSV files...") # Changed log message
389| 
390| # Define the final header order: start with core fields, then add sorted custom fields
391| final_headers = core_headers + sorted([h for h in all_field_names if h not in core_headers])
392| 
393| # Write the original snapshot file
394| write_csv(OUTPUT_PATH, processed_data, final_headers)
395| 
396| # Write the 'latest_snapshot.csv' file (overwrites if exists)
397| write_csv(LATEST_OUTPUT_PATH, processed_data, final_headers)
398| 
399| print("All CSV files written successfully.") # Changed log message
400| 
401| # --- Set output for workflow using environment file (for the original dated snapshot) ---\n402| output_env_file = os.environ.get("GITHUB_OUTPUT")
403| 
404| if output_env_file:
405|     print(f"Setting output 'snapshot_filename' in {output_env_file} for {OUTPUT_PATH}")
406|     try:
407|         with open(output_env_file, "a") as f: # Open in append mode
408|             f.write(f"snapshot_filename={OUTPUT_PATH}\\n")
409|             # Also set an output for the latest snapshot, in case the workflow needs it
410|             f.write(f"latest_snapshot_filename={LATEST_OUTPUT_PATH}\\n")
411|         print("Outputs set successfully.")
412|     except Exception as e:
413|         print(f"Error writing to GITHUB_OUTPUT file '{output_env_file}': {e}", file=sys.stderr)
414| else:
415|     print("Warning: GITHUB_OUTPUT environment variable not set. Cannot pass output to subsequent steps.", file=sys.stderr)
416| 
