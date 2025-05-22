import json
import os
import uuid
import datetime
# from zoneinfo import ZoneInfo # Not needed for current tool logic
from typing import Any, Dict, List

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents import Agent
# Remove LiteLlm import and config
# from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types # Keep this for ADK types

# Import Google Generative AI SDK (will pick up GOOGLE_API_KEY from environment)
import google.genai as genai # <--- Import the SDK

from dotenv import load_dotenv
import traceback

# Add aiosqlite import (keeping SQLite as per your last working DB code)
import aiosqlite

# --- Load environment variables early ---
load_dotenv() # <--- Load variables from .env

# --- API Configuration (for Google Generative AI) ---
# Get Google API Key from environment variables

API_KEY = " "
API_URL = " "


# Note: We are NOT calling genai.configure(api_key=...) here.
# The SDK should pick up the GOOGLE_API_KEY environment variable automatically.


# --- Data Storage (Global variables) ---
product_catalog: List[Dict[str, Any]] = []

# Define the paths to your static data files
PRODUCTS_FILE = "products.json"


# --- Database Configuration (For SQLite) ---
# Use the environment variable for the SQLite database file path
SQLITE_DATABASE_PATH = os.getenv("SQLITE_DATABASE_PATH", "./ecommerce.db") # Default to ./ecommerce.db

# Global variable to hold the database path
db_file_path = SQLITE_DATABASE_PATH


# Define a Default User ID (Still needed for the orders table)
DEFAULT_USER_ID = "Aryan Sharma"


# Initialize an async HTTP client (kept)
# Set verify=True in production for SSL cert verification
async_client = httpx.AsyncClient(verify=False)


# --- Simulated Tool Definitions (Using aiosqlite) ---

# search_products remains the same (uses product_catalog from JSON)
async def search_products(query: str) -> Dict[str, Any]:
    """
    Simulates searching a product catalog loaded from JSON.
    Returns a list of products or a not found message.
    """
    print(f"[Tool Call] search_products called for query: '{query}'")
    print(f"DEBUG: search_products received query: '{query}'")

    query_lower = query.lower()
    found_products = []
    keywords = query_lower.split()

    if not keywords:
        return {"status": "not_found", "message": "Please provide keywords."}

    global product_catalog
    if not product_catalog:
        return {"status": "error", "message": "Product catalog is empty."}

    print(f"DEBUG: Keywords to search for: {keywords}")

    if "what" in query_lower and "categories" in query_lower:
        categories = set()
        print("DEBUG: Inside the 'what categories' block")
        for product in product_catalog:
            print(f"DEBUG: Checking product: {product}")
            if isinstance(product, dict) and "category" in product:
                categories.add(product["category"])
                print(f"DEBUG: Added category: {product['category']}")
        if categories:
            category_list = list(categories)
            report_message = f"Available product categories are: {', '.join(category_list)}."
            result = {"status": "report", "report": report_message}
            print(f"DEBUG: search_products returning: {result}")
            return result
        else:
            result = {"status": "not_found", "message": "No product categories found."}
            print(f"DEBUG: search_products returning: {result}")
            return result
    elif "total" in query_lower and "product" in query_lower and "count" in query_lower:
        total_count = len(product_catalog)
        report_message = f"There are currently {total_count} products in our catalog."
        result = {"status": "report", "report": report_message}
        print(f"DEBUG: search_products returning: {result}")
        return result

    # *Moved the total product count check to be *before* the keyword search*

    for product in product_catalog:
        if not isinstance(product, dict):
            print(f"WARNING: Skipping invalid product: {product}")
            continue

        name = product.get('name', '').lower()
        description = product.get('description', '').lower()
        category = product.get('category', '').lower()
        product_text = f"{name} {description} {category}"

        if "computer" in query_lower and "accessories" in query_lower:
            if "electronics" in category or "home & office" in category:
                if "mouse" in name.lower() or "keyboard" in name.lower() or "speaker" in name.lower() or "headphone" in name.lower():
                  found_products.append(product)
                  print(f"DEBUG: Found a match: {product.get('name')}")
        elif any(keyword in product_text for keyword in keywords):
            found_products.append(product)
            print(f"DEBUG: Found a match: {product.get('name')}")

    if found_products:
        results_list = []
        for product in found_products:
            price = product.get('price', 0.0)
            if not isinstance(price, (int, float)):
                print(f"WARNING: Non-numeric price for {product.get('id')}: {price}")
                price = 0.0
            results_list.append(
                f"{product.get('name', 'Unknown Product')} (ID: {product.get('id', 'N/A')}, Price: ${price:.2f})"
            )
        report_message = f"I found {len(found_products)} product(s) matching '{query}': " + "; ".join(results_list) + "."
        result = {"status": "report", "report": report_message}
        print(f"DEBUG: search_products returning: {result}")
        return result
    else:
        result = {"status": "not_found", "message": f"Sorry, no products found matching '{query}'."}
        print(f"DEBUG: search_products returning: {result}")
        return result




# check_order_status - UPDATED to retrieve stored total_price
async def check_order_status(order_id: str) -> Dict[str, Any]: # Changed return type hint to Any as it can return error/not_found too
    """
    Checks the status of an order in the SQLite database, including item prices and the stored total.
    """
    print(f"[Tool Call] check_order_status called for order_id: '{order_id}'")

    if not db_file_path:
         print("   Database file path is not set.")
         return {
             "status": "error",
             "message": "Database is not configured. Cannot check order status.",
         }

    try:
        async with aiosqlite.connect(db_file_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            db.row_factory = aiosqlite.Row
            cursor = await db.cursor()

            # SQL query to fetch order and its items, including price from order_items
            # Select total_price from orders table
            sql = """
            SELECT
                o.order_id, o.status, o.created_at, o.details, o.total_price,
                oi.product_id, oi.quantity, oi.price
            FROM orders o
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_id = ?
            """
            await cursor.execute(sql, (order_id,))
            results = await cursor.fetchall()

            if not results:
                print(f"   Order ID '{order_id}' not found in database.")
                return {
                    "status": "not_found",
                    "message": f"Order with ID {order_id} not found.",
                }

            # Process results
            order_data = results[0]
            status = order_data.get('status', 'Unknown')
            created_at = order_data.get('created_at', 'N/A')
            details = order_data.get('details', 'No additional details available.')
            stored_total_price = order_data.get('total_price', 0.0) # Retrieve stored total


            item_details_list = []
            # We can still calculate the total here for verification if needed, but will use the stored value
            # calculated_total = 0.0


            # Check if the order had items (at least one row with a product_id that is not NULL)
            # The LEFT JOIN will return one row with NULLs for oi columns if order exists but has no items
            if order_data and order_data['product_id'] is not None: # Ensure product_id is not None from LEFT JOIN
                 for row in results:
                      item_product_id = row.get('product_id')
                      item_quantity = row.get('quantity', 0) # Default quantity to 0 for calculation safety
                      item_price = row.get('price', 0.0)    # Default price to 0.0 for calculation safety

                      # Look up product name from loaded JSON catalog (optional, price is from DB)
                      product = next((p for p in product_catalog if p.get("id") == item_product_id), None)
                      product_name = product.get("name", f"Unknown Product ({item_product_id})") if product else f"Unknown Product ({item_product_id})"

                      item_cost = item_quantity * item_price
                      # calculated_total += item_cost

                      # Include item-level price and calculated cost
                      item_details_list.append(f"- {item_quantity} x {product_name} @ ${item_price:.2f} each (${item_cost:.2f})")

            items_summary = "\n".join(item_details_list) if item_details_list else "No items listed."


            report_message = (
                f"Details for order {order_id} (Placed On: {created_at}):\n"
                f"Status: {status}\n"
                f"Items:\n{items_summary}\n"
                f"Total Amount: ${stored_total_price:.2f}\n" # Use the stored total
                f"More Info: {details}"
            )

            return {
                "status": "report",
                "report": report_message,
            }

    except Exception as e:
        print(f"Error checking order status for '{order_id}': {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"An error occurred while checking status for order '{order_id}': {e}",
        }

async def place_order(items: List[Dict[str, int]]) -> Dict[str, Any]:
    """
    Places an order for one or more products by adding them to the SQLite database.
    Expects a list of dictionaries, where each dictionary contains 'product_id' and 'quantity'.
    """
    print(f"[Tool Call] place_order called with items: {items}")
    if not db_file_path:
        print("    Database file path is not set.")
        return {
            "status": "error",
            "message": "Database is not configured. Cannot place order.",
        }

    order_items_details = []
    order_total_cost = 0.0
    all_products_found = True
    failed_product_ids = []

    # 1. Validate product existence and quantities for all items
    for item in items:
        product_id = item.get("product_id")
        quantity = item.get("quantity", 1)

        if not product_id:
            print("    Error: product_id is missing in an item.")
            return {"status": "error", "message": "Invalid order item: product ID is missing."}

        product = next((p for p in product_catalog if p.get("id") == product_id), None)
        if not product:
            print(f"    Product ID '{product_id}' not found in catalog.")
            all_products_found = False
            failed_product_ids.append(product_id)
            continue  # Process other items to report all missing products

        product_price = product.get("price", 0.0)
        if not isinstance(product_price, (int, float)) or product_price < 0:
            print(f"    Product '{product_id}' has invalid or missing price: {product_price}")
            return {"status": "error", "message": f"Product '{product_id}' has an invalid price. Cannot place order."}

        if not isinstance(quantity, int) or quantity <= 0:
            print(f"    Invalid quantity: {quantity} for product '{product_id}'. Must be a positive integer.")
            return {"status": "error", "message": f"Invalid quantity for product '{product_id}'. Please specify a valid positive number."}

        item_cost = quantity * product_price
        order_total_cost += item_cost
        order_items_details.append({"product_id": product_id, "quantity": quantity, "price": product_price, "name": product.get("name", "Unknown")})

    if not all_products_found:
        return {
            "status": "error",
            "message": f"The following product IDs were not found in the catalog: {', '.join(failed_product_ids)}.",
        }

    try:
        async with aiosqlite.connect(db_file_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            cursor = await db.cursor()

            # 2. Generate unique order ID
            new_order_id = str(uuid.uuid4())

            # 3. Insert the new order into the 'orders' table
            order_details_str = ", ".join([f"{item['quantity']} x {item['name']} @ ${item['price']:.2f}" for item in order_items_details])
            order_sql = """
                INSERT INTO orders (order_id, user_id, status, created_at, details, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """
            order_values = (
                new_order_id,
                DEFAULT_USER_ID,
                "Processing",
                datetime.datetime.now().isoformat(),
                f"Order placed via AI assistant for: {order_details_str}",
                order_total_cost,
            )
            await cursor.execute(order_sql, order_values)

            # 4. Insert items into the 'order_items' table
            item_sql = """
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (?, ?, ?, ?)
                """
            for item in order_items_details:
                item_values = (new_order_id, item["product_id"], item["quantity"], item["price"])
                await cursor.execute(item_sql, item_values)

            # 5. Commit the transaction
            await db.commit()

            print(f"    Order {new_order_id} committed to database with total cost ${order_total_cost:.2f}.")

            # 6. Return success response
            ordered_items_summary = ", ".join([f"{item['quantity']} x {item['name']}" for item in order_items_details])
            return {
                "status": "success",
                "order_id": new_order_id,
                "message": f"Your order for {ordered_items_summary} has been placed successfully! Total cost: ${order_total_cost:.2f}. Your order ID is {new_order_id}.",
            }

    except Exception as e:
        print(f"Error placing order for items {items}: {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"An error occurred while placing your order: {e}",
        }

# remove_order tool implementation (called by order_cancellation_agent) - Remains the same
async def remove_order(order_id: str) -> Dict[str, str]:
    """
    Removes or cancels an order and its items from the SQLite database by order ID.
    """
    print(f"[Tool Call] remove_order called for order_id: '{order_id}'")

    if not db_file_path:
         print("   Database file path is not set.")
         return {
             "status": "error",
             "message": "Database is not configured. Cannot remove order.",
         }

    try:
        async with aiosqlite.connect(db_file_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")

            # Check if the order exists first
            check_sql = "SELECT COUNT(*) FROM orders WHERE order_id = ?"
            cursor = await db.cursor()
            await cursor.execute(check_sql, (order_id,))
            exists = (await cursor.fetchone())[0] > 0

            if not exists:
                 print(f"   Order ID '{order_id}' not found in database.")
                 return {
                     "status": "not_found",
                     "message": f"Order with ID {order_id} not found. Cannot remove.",
                 }

            # Delete order items first (due to foreign key constraint)
            delete_items_sql = "DELETE FROM order_items WHERE order_id = ?"
            await cursor.execute(delete_items_sql, (order_id,))
            items_deleted = cursor.rowcount

            # Delete the order itself
            delete_order_sql = "DELETE FROM orders WHERE order_id = ?"
            await cursor.execute(delete_order_sql, (order_id,))
            order_deleted = cursor.rowcount

            await db.commit()

            print(f"   Order {order_id} and {items_deleted} items removed from database.")

            return {
                "status": "success",
                "order_id": order_id,
                "message": f"Order {order_id} has been successfully removed.",
            }

    except Exception as e:
        print(f"Error removing order '{order_id}': {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"An error occurred while removing order '{order_id}': {e}",
        }

# --- NEW Tool: List All Orders - UPDATED to format as HTML table ---
async def list_all_orders() -> Dict[str, Any]:
    """
    Fetches and lists all orders from the SQLite database and formats as an HTML table string.
    """
    print("[Tool Call] list_all_orders called")

    if not db_file_path:
         print("   Database file path is not set.")
         return {
             "status": "error",
             "message": "Database is not configured. Cannot list orders.",
         }

    try:
        async with aiosqlite.connect(db_file_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            db.row_factory = aiosqlite.Row # Rows behave like dictionaries
            cursor = await db.cursor()

            # Select relevant columns from the orders table
            sql = """
            SELECT order_id, status, created_at, total_price
            FROM orders
            ORDER BY created_at DESC; -- Order by most recent first
            """
            await cursor.execute(sql)
            results = await cursor.fetchall()

            if not results:
                print("   No orders found in database.")
                return {
                    "status": "not_found",
                    "message": "You have not placed any orders yet.",
                }

            # *** Format results as an HTML table string ***
            table_rows = []
            # Add table header
            table_rows.append("<tr><th>Order ID</th><th>Status</th><th>Total</th><th>Placed On</th></tr>")

            for row in results:
                # *** Corrected: Access columns using square brackets [] ***
                order_id = row['order_id']
                status = row['status']
                created_at = row['created_at']
                total_price = row['total_price']
                # Add a row for each order
                table_rows.append(
                    f"<tr>"
                    f"<td>{order_id}</td>"
                    f"<td>{status}</td>"
                    f"<td>${total_price:.2f}</td>"
                    f"<td>{created_at}</td>" # Display the datetime string directly
                    f"</tr>"
                )

            # Combine all rows into a full HTML table
            # Added a class "orders-table" for specific styling if needed
            html_table = "<table class='orders-table'>" + "".join(table_rows) + "</table>"

            # The tool should return a dictionary. The agent will use the 'report' field.
            return {
                "status": "report",
                "report": html_table, # Put the HTML string here
                # Optionally, add a plain text intro message for the agent to use
                "intro_message": "Here is your order history:",
            }


    except Exception as e:
        print(f"Error listing all orders: {e}")
        traceback.print_exc()
        # Return an error status if something goes wrong
        return {
            "status": "error",
            "message": f"An error occurred while listing orders: {e}",
        }


# --- Configure Agents (Using LiteLlm) ---
# Re-using the LiteLlm config provided for all agents
llm_config = LiteLlm(
    model="gpt-4o-mini",
    api_key=API_KEY,
    api_base=API_URL,
    # Add any other LiteLlm specific configs here if needed
)
# Use the defined llm_config for all agents

greeting_agent = Agent(
    model=llm_config,
    name="greeting_agent",
    instruction="You are the Greeting Agent. Your ONLY task is to provide a friendly and concise greeting.",
    description="Handles simple greetings and hellos",
)

farewell_agent = Agent(
    model=llm_config,
    name="farewell_agent",
    instruction="You are the Farewell Agent. Your ONLY task is to provide a polite and concise goodbye message.",
    description="Handles simple farewells and goodbyes",
)

product_search_agent = Agent(
    model=llm_config,
    name="product_search_agent",
    instruction="""You are the Product Search Agent. Your primary goal is to understand user queries related to finding products. Your responses should be in plain text, avoiding any special formatting.

Here's how to handle user queries:

**1. Direct Product Search:**

* If the user provides specific keywords or product names (e.g., 'smartphone', 'running shoes', 'wireless keyboard'), immediately use the `search_products` tool with those keywords.

**2. Broad Category Handling:**

* If the user mentions a broad category (e.g., 'electronics', 'clothing', 'computer accessories'):
    * First, identify the mentioned category.
    * Then, check if the `search_products` tool, when used with this broad category, returns any results.
        * If results are found, present them to the user, addressing them by name if known (e.g., "Here are some products I found in the [category] category, [User Name]: ...").
        * If no results are found, ask the user to specify a sub-category or a specific product within that category to narrow down the search (e.g., "I found some products in the [category] category, but to help me find exactly what you're looking for, could you please specify a sub-category or a specific product?").

**3. Category Listing Request:**

* If the user asks for a list of categories (e.g., "What product categories do you have?", "List all categories"):
    * Use the `search_products` tool with a query like "what categories".  The `search_products` tool is now designed to handle this and return a list of categories.
    * Present the categories to the user, addressing them by name if known (e.g., "Here are the product categories I can search, [User Name]: [category list]").

**4. No Products Found:**

* After using the `search_products` tool, if no results are found:
    * Inform the user politely, addressing them by name if known (e.g., "I'm sorry, [User Name], I couldn't find any products matching your query.").
    * If the query was for a specific item, suggest searching within a broader category (e.g., "I couldn't find a 'mechanical keyboard', but I can search for 'keyboards' in general.").
    * If the query was for a broad category and no sub-categories were found, inform the user.

**5. Total Product Count Request:**

    * If the user asks for the total number of products (e.g., "How many products do you have?", "What is the total number of products?"):
    * Use the `search_products` tool with the query "total product count". The `search_products` tool is now designed to handle this and return the total count.
    * Present the count to the user, addressing them by name if known (e.g., "There are currently [total count] products in our catalog, [User Name].").
**6. Presenting Results:**

* When presenting results from the `search_products` tool (when the tool returns 'status' is 'report'):
    * Present the information from the 'report' field to the user in a clear and concise manner, addressing them by name if known (e.g., "Here's what I found for you, [User Name]: ...").

**Example Interaction:**

User: "Show me computer accessories"
Agent: *(Internally calls search_products with "computer accessories")* "Here are some products I found in the computer accessories category, [User Name]: ..."

User: "I want a mechanical keyboard"
Agent: *(Internally calls search_products with "mechanical keyboard")* "I'm sorry, [User Name], I couldn't find any products matching 'mechanical keyboard'.  I can search for 'keyboards' in general, would you like me to do that?"

User: "show me electronics"
Agent: *(Internally calls search_products with "electronics")* "Here are some products I found in the electronics category, [User Name]: ..."

User: "laptops"
Agent: *(Internally calls search_products with "laptops")* "Here's what I found for you, [User Name]: ..."

User: "What product categories do you have?"
Agent: *(Internally calls search_products with "what categories do you have?")* "Here are the product categories I can search, [User Name]: Clothing, Footwear, Accessories, Electronics, Fitness, Home & Kitchen, Books, Home & Office, Smart Home, Garden & Outdoor, Tools, Home Decor, Kitchen Appliances, Dinnerware, Cookware, Cutlery, Kitchen Utensils, Home & Storage, Bathroom, Bedding, Lighting, Rugs, Window Treatments, Cleaning Supplies, Bathroom Accessories, Personal Care, Fitness Supplements, Sports, Health."

**Example Interaction:**

User: "How many products do you have?"
Agent: *(Internally calls search_products with "total product count")* "There are currently 102 products in our catalog, Aryan."

""",
    description="Searches for products in the catalog based on user queries, with category refinement.",
    tools=[search_products],
)




# order_status_agent - Instruction UPDATED slightly
order_status_agent = Agent(
    model=llm_config,
    name="order_status_agent",
    instruction="""You are the Order Status Agent. Your task is to help users check the status of their orders. Identify the order ID from the user's message, however it is phrased. Use the `check_order_status` tool with the extracted order ID.

Examples of user queries:
- 'What is the status of my order #12345?' -> Order ID: 12345
- 'Can you tell me where my order with ID ABC-678 is?' -> Order ID: ABC-678
- 'Track order number 9876.' -> Order ID: 9876
- 'Check the status of order XYZ123.' -> Order ID: XYZ123
- 'I want to know about my recent purchase, the ID is 54321.' -> Order ID: 54321

Based on the tool's response, if the 'status' is 'report', provide the detailed order information, including item prices and the total amount, to the user clearly. If the 'status' is 'not_found', inform the user that the order ID was not found. Respond in plain text, avoiding any special formatting.""",
    description="Checks the status of a user's order based on the provided order ID, including item prices and total amount.",
    tools=[check_order_status],
)

ordering_agent = Agent(
    model=llm_config,
    name="ordering_agent",
    instruction="""You are the Ordering Agent. Your role is to process user requests to place orders for one or more products. Understand the user's intent to buy products and extract a list of product IDs and their desired quantities.

Examples of user queries:
- 'I want to order product ID: XYZ-123 and two of ABC-456.' -> items: [{'product_id': 'XYZ-123', 'quantity': 1}, {'product_id': 'ABC-456', 'quantity': 2}]
- 'Can you buy me one of LMN-789 and three of PQR-001?' -> items: [{'product_id': 'LMN-789', 'quantity': 1}, {'product_id': 'PQR-001', 'quantity': 3}]
- 'Order item 111 and two of item 222.' -> items: [{'product_id': '111', 'quantity': 1}, {'product_id': '222', 'quantity': 2}]

Call the `place_order` tool with the extracted list of items. Based on the tool's response ('success' or 'error'), inform the user if the order was placed successfully, providing the order ID and the total cost (which the tool will now need to calculate for multiple items) from the 'message' if successful, or the 'message' if there was an error. If you cannot extract a clear list of product IDs and quantities, ask the user for clarification. Respond concisely and in plain text, avoiding Markdown or special formatting.
    """,
    description="Places new orders for one or more products based on user requests, tracking the price at the time of order.",
    tools=[place_order],
)

order_cancellation_agent = Agent(
    model=llm_config,
    name="order_cancellation_agent",
    instruction="""You are the Order Cancellation Agent. Your task is to process user requests to cancel or remove orders. Identify the order ID that the user wants to cancel, regardless of how they phrase their request. Use the `remove_order` tool with the extracted order ID.

Examples of user queries:
- 'Cancel order #56789.' -> Order ID: 56789
- 'I want to remove my order with ID LMN-321.' -> Order ID: LMN-321
- 'Can you delete order number 11223?' -> Order ID: 11223
- 'I need to cancel a recent purchase, the ID is PQR-777.' -> Order ID: PQR-777
- 'Get rid of order number 44556.' -> Order ID: 44556

Based on the tool's response, if the 'status' is 'success', confirm to the user that the order has been successfully removed. If the 'status' is 'not_found', inform the user that the order ID was not found. If the 'status' is 'error', relay the error message from the tool. If you cannot clearly identify the order ID, ask the user for the specific ID they wish to cancel. Respond in plain text, avoiding any special formatting.""",
    description="Cancels or removes existing orders based on the provided order ID.",
    tools=[remove_order],
)


# --- NEW Agent: List Orders ---
list_orders_agent = Agent(
    model=llm_config,
    name="list_orders_agent",
    instruction="""You are the List Orders Agent. Your purpose is to show the user their order history. When the user asks to see their orders or order history, simply call the `list_all_orders` tool.

Examples of user queries:
- 'Show me my orders.'
- 'What have I ordered before?'
- 'Can I see my order history?'
- 'List all my past purchases.'
- 'What are my previous orders?'

Based on the tool's response, if the 'status' is 'report', present the information from the 'report' field (which will be an HTML table) to the user. If the 'status' is 'not_found', inform the user using the message from the 'message' field (e.g., "You have not placed any orders yet."). Respond in plain text, avoiding any special formatting of the HTML content.""",
    description="Lists all orders placed by the user.",
    tools=[list_all_orders],
)


# Root Orchestrator Agent - Instruction UPDATED and sub_agents UPDATED
root_agent = Agent(
    model=llm_config,
    name="shopping_orchestrator_agent",
    instruction=f"""You are the main Shopping Assistant. Your primary role is to greet the user, introduce yourself and your capabilities, ask for their name, and then route their subsequent requests to the most appropriate specialist agent. Be concise in your routing decisions.

**Initial Interaction:**

1. Introduce yourself as the Shopping Assistant.
2. Briefly list your capabilities: product search, checking order status, placing orders, listing all orders, and cancelling orders.
3. Ask the user for their name (e.g., 'What is your name?').
4. Once you receive the user's name, remember it for future interactions.
5. Always use the first name of the user.(e.g., if user says "My name is Aryan Sharma", remember "Aryan" for future interactions).

**Subsequent Interactions:**

- **Greeting:** If the user's message is a clear greeting (e.g., "Hi", "Hello", "Good morning"), delegate to `greeting_agent`, passing the user's name if known.
- **Farewell:** If the user's message is a clear farewell (e.g., "Bye", "Goodbye", "See you"), delegate to `farewell_agent`, passing the user's name if known.
- **Capabilities Inquiry:** If the user asks about your capabilities again (e.g., "What can you do?"), respond directly with the list of capabilities, addressing them by name if known (e.g., '[User Name], as I mentioned, I can help with product search, checking order status, placing orders, listing all orders, and cancelling orders.').
- **Product Search:** If the user expresses a desire to find products, including category listing and total product count, delegate to `product_search_agent`, passing the user's name if known. Examples: "search for [product]", "find me [item]", "show me [category]", "what product categories do you have?", "how many products do you have?".
- **Order Status:** If the user asks about the status of a specific order (usually including an order ID or phrases like "where is my order"), delegate to `order_status_agent`, passing the user's name if known.
- **Ordering:** If the user wants to buy or order a product (usually including a product ID or keywords like "buy", "order", "purchase"), delegate to `ordering_agent`, passing the user's name if known.
- **Order Cancellation:** If the user wants to cancel or remove an order (usually including an order ID or keywords like "cancel", "remove", "delete order"), delegate to `order_cancellation_agent`, passing the user's name if known.
- **List Orders:** If the user wants to see their order history (e.g., "list my orders", "show me my order history", "what have I ordered"), delegate to `list_orders_agent`, passing the user's name if known.

**Direct Responses (after initial interaction):**

- For queries that do not clearly fall into one of the delegation categories, politely state, addressing them by name if known (e.g., '[User Name], I can only help with product search, checking order status, placing orders, listing all orders, and cancelling orders. Please let me know how I can assist you with these tasks.').
""",
    description="Greets the user, introduces capabilities, asks for name, and then routes user queries to specialized agents.",
    tools=[],
    sub_agents=[
        greeting_agent,
        farewell_agent,
        product_search_agent,
        order_status_agent,
        ordering_agent,
        order_cancellation_agent,
        list_orders_agent,
    ],
)



# --- FastAPI App Setup ---
app = FastAPI()

# Ensure only one mount for static files
app.mount("/static", StaticFiles(directory="templates/static"), name="static")

session_service = InMemorySessionService()
runner: Runner = None
user_name_cache: Dict[str, str] = {} # Simple in-memory cache for user names

# Using DEFAULT_USER_ID defined at the top for session management
APP_NAME = "my_adk_fastapi_app"
USER_ID_FOR_SESSIONS = DEFAULT_USER_ID # Consistent user ID for sessions
SESSION_ID = "fastapi_session_abc" # Keep a fixed session ID for simplicity


@app.on_event("startup")
async def startup_event():
    """Initializes ADK components, HTTP client, loads static data, and sets DB file path."""
    global runner, product_catalog, db_file_path
    print("Initializing ADK Session and Runner...")

    # --- Load Static Data (products still from JSON) ---
    print(f"Loading product data from {PRODUCTS_FILE}...")
    try:
        with open(PRODUCTS_FILE, "r") as f:
            product_catalog = json.load(f)
        print(f"Loaded {len(product_catalog)} products from {PRODUCTS_FILE}")
    except FileNotFoundError:
        print(f"Error: {PRODUCTS_FILE} not found. Product search and ordering will not work correctly.")
        product_catalog = []
    except json.JSONDecodeError:
        print(f"Error: Could not decode {PRODUCTS_FILE}. Check file format.")
        product_catalog = []

    # --- Database Setup (SQLite) ---
    db_file_path = SQLITE_DATABASE_PATH
    print(f"Using SQLite database file: {db_file_path}")

    # Optional: Create tables on startup if they don't exist
    try:
        async with aiosqlite.connect(db_file_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255),
                    status VARCHAR(50),
                    created_at DATETIME,
                    details TEXT,
                    total_price REAL DEFAULT 0.0 -- Added column to store total price of the order
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id VARCHAR(255),
                    product_id VARCHAR(255),
                    quantity INTEGER,
                    price REAL, -- Stores unit price at time of order
                    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
                )
            """)
            await db.commit()
            print("SQLite database tables checked/created.")
    except Exception as e:
        print(f"Error checking/creating SQLite tables: {e}")
        traceback.print_exc()

    # --- ADK Session and Runner Setup ---
    try:
        # Use the consistent user ID for sessions
        session = session_service.get_session(app_name=APP_NAME, user_id=USER_ID_FOR_SESSIONS, session_id=SESSION_ID)
        if session is None:
             session_service.create_session(app_name=APP_NAME, user_id=USER_ID_FOR_SESSIONS, session_id=SESSION_ID)
             print(f"Created session: {SESSION_ID}")
        else:
             print(f"Using existing session: {SESSION_ID}")
    except Exception as e:
        print(f"Error managing session {SESSION_ID}: {e}")

    # --- Initialize the Runner ---
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        # No need to pass API key here, SDK should pick it up from env
        session_service=session_service
    )
    print("ADK Runner initialized with Root Agent.")


@app.on_event("shutdown")
async def shutdown_event():
    """Shuts down the HTTP client."""
    print("Shutting down HTTP client...")
    await async_client.close()
    print("HTTP client shut down.")


# --- FastAPI Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the index.html file."""
    try:
        return FileResponse("templates/index.html")
    except FileNotFoundError:
        return HTMLResponse("<html><body><h1>Error: index.html not found in the 'templates' directory.</h1></body></html>", status_code=404)


@app.post("/chat")
async def chat_endpoint(message: Dict[str, str]):
    """
    Receives user message, runs through ADK agent (delegation),
    and returns the final text response.
    """
    if runner is None:
        print("Error: Runner is not initialized during chat request.")
        events = [{"type": "error", "message": "Agent system is not fully initialized.", "status_code": 500}]
        return JSONResponse(content={"response": "Agent system is not fully initialized.", "events": events}, status_code=500)

    user_message = message.get("message", "").strip()
    if not user_message:
        events = [{"type": "error", "message": "Please provide a message.", "status_code": 400}]
        return JSONResponse(content={"response": "Please provide a message.", "events": events}, status_code=400)

    print(f"\n--- Received message: {user_message} ---")

    try:
        user_content = types.Content(role='user', parts=[types.Part(text=user_message)])
        print(f"Created input content: {user_content}")
    except Exception as e:
        print(f"Error creating types.Content object: {e}")
        events = [{"type": "error", "message": f"Error processing message input: {e}", "status_code": 500}]
        return JSONResponse(content={"response": f"Error processing message input: {e}", "events": events}, status_code=500)

    final_response = None
    agent_name = "Shopping Assistant"
    events = []
    last_distinct_agent = None

    try:
        async for event in runner.run_async(user_id=USER_ID_FOR_SESSIONS, session_id=SESSION_ID, new_message=user_content):
            current_agent = getattr(event, 'author', None)
            print(f"Runner yielded event type: {getattr(event, 'type', 'N/A')}, Author: {current_agent}")

            if current_agent and last_distinct_agent and current_agent != last_distinct_agent:
                events.append({"type": "agent_transfer", "from": last_distinct_agent, "to": current_agent})

            if current_agent:
                last_distinct_agent = current_agent

            if (hasattr(event, 'is_final_response') and event.is_final_response() and
                hasattr(event, 'content') and event.content and
                hasattr(event.content, 'parts') and event.content.parts
               ):
                if hasattr(event.content.parts[0], 'text') and event.content.parts[0].text:
                    final_response = event.content.parts[0].text
                    agent_name = current_agent or "Shopping Assistant"
                    events.append({"type": "final_response", "text": final_response, "agent_name": agent_name})
            elif hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts and hasattr(event.content.parts[0], 'text'):
                # Capture intermediate messages as well, with the author
                message_text = event.content.parts[0].text
                message_author = current_agent or "System" # Default to System if no author
                events.append({"type": "intermediate_message", "author": message_author, "text": message_text})

    except Exception as e:
        print(f"--- An error occurred during runner execution: {e} ---")
        traceback.print_exc()
        error_message = f"An internal server error occurred: {e}. Check server logs for details."
        if "Missing key inputs argument" in str(e) or "api_key" in str(e).lower():
            error_message = "Error: The AI model could not be accessed. Please ensure your Google API key is correctly set in the environment variable GOOGLE_API_KEY."
        events.append({"type": "error", "message": error_message, "status_code": 500, "agent_name": agent_name})

    # Construct and return the JSONResponse *after* the try-except block
    if final_response:
        try:
            parsed_json = json.loads(final_response)
            return JSONResponse(content={"response": parsed_json, "agent_name": agent_name, "events": events})
        except (json.JSONDecodeError, TypeError):
            return JSONResponse(content={"response": final_response, "agent_name": agent_name, "events": events})
    else:
        return JSONResponse(content={"response": "No final response received.", "agent_name": agent_name, "events": events}, status_code=500)
# --- How to run ---
# 1. Save the code as main.py
# 2. Create the 'templates' folder with index.html, style.css, script.js
# 3. Create products.json in the same directory as main.py
# 4. Create/Update a .env file with your Google API key and SQLite database path:
#    GOOGLE_API_KEY=YOUR_ACTUAL_GOOGLE_API_KEY
#    SQLITE_DATABASE_PATH=./ecommerce.db
# 5. Install necessary libraries: pip install fastapi uvicorn google-adk google-generativeai python-dotenv httpx aiosqlite
# 6. Make sure your GOOGLE_API_KEY environment variable is correctly set via the .env file.
#    When you run uvicorn, check the terminal output for the "DEBUG: GOOGLE_API_KEY loaded from environment:" line
#    to confirm your key is being loaded.
# 7. Run: uvicorn main:app --reload