import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
from streamlit_gsheets import GSheetsConnection

# --- 0. PAGE CONFIG MUST BE THE VERY FIRST COMMAND ---
st.set_page_config(page_title="Shop Ledger", layout="wide")

# --- CUSTOM CSS FOR LARGER FONTS ---
st.markdown("""
<style>
    input[type="text"], input[type="number"] { font-size: 1.2rem !important; }
    .stSelectbox label, .stTextInput label, .stNumberInput label { font-size: 1.1rem !important; font-weight: bold !important; }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { font-family: sans-serif; }
    div[role="radiogroup"] { padding-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 1. GOOGLE SHEETS SETUP ---
def get_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # Read the sheet (ttl=0 ensures we always get live data)
        df = conn.read(worksheet="Sheet1", ttl=0)
        df = df.dropna(how="all") # Drop completely empty rows Google Sheets sometimes adds
        df.fillna("", inplace=True) # Fix empty cells turning into "NaN"
        
        # Enforce correct data types for math columns
        df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(1).astype(int)
        df['Total Price'] = pd.to_numeric(df['Total Price'], errors='coerce').fillna(0.0)
        
        # --- THE FIX: Force text columns to be strictly strings ---
        df['hidden_id'] = df['hidden_id'].astype(str)
        df['Phone'] = df['Phone'].astype(str).replace("nan", "") # Extra safeguard for empty cells
        df['Name'] = df['Name'].astype(str)
        df['Status'] = df['Status'].astype(str)
        df['Date'] = df['Date'].astype(str)
        
        return df
    except Exception:
        # If the sheet is empty or brand new, create the structure
        return pd.DataFrame(columns=['hidden_id', 'Date', 'Name', 'Qty', 'Total Price', 'Phone', 'Status'])
def save_data(df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(worksheet="Sheet1", data=df)
    st.cache_data.clear() # Clear cache so next read is totally fresh

# --- 2. STREAMLIT UI & NAVIGATION ---
st.title("📦 Daily Shop Ledger")

# --- FLASH MESSAGES ---
if 'flash_success' in st.session_state:
    st.success(st.session_state.flash_success)
    del st.session_state.flash_success
if 'flash_error' in st.session_state:
    st.error(st.session_state.flash_error)
    del st.session_state.flash_error

# --- PERSISTENT NAVIGATION MENU ---
menu_options = ["📊 Dashboard", "➕ Add Entry", "🔍 Search", "✏️ Edit / Delete"]
current_tab = st.radio("Navigation Menu", menu_options, horizontal=True, label_visibility="collapsed", key="main_nav")
st.divider()

# --- TAB 1: DASHBOARD ---
if current_tab == "📊 Dashboard":
    df = get_data()
    today_str = datetime.today().strftime('%Y-%m-%d')
    yesterday_str = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    st.header("🤝 Pending Borrowed Items")
    if not df.empty:
        borrowed_df = df[df['Status'] == 'Borrowed']
    else:
        borrowed_df = pd.DataFrame()
    
    if borrowed_df.empty:
        st.info("No outstanding borrowed items!")
    else:
        for _, row in borrowed_df.iterrows():
            col1, col2, col3, col4 = st.columns([1.5, 3, 2, 1.5])
            col1.write(f"**{row['Date']}**")
            col2.write(f"**{row['Name']}** (Qty: {row['Qty']})")
            col3.write(f"📞 {row['Phone']} | **₹{row['Total Price']}**")
            
            if col4.button("✔️ Mark Paid", key=f"pay_{row['hidden_id']}", use_container_width=True):
                df.loc[df['hidden_id'] == row['hidden_id'], 'Status'] = 'Paid'
                save_data(df)
                st.session_state.flash_success = f"Marked '{row['Name']}' as paid!"
                st.rerun()

    st.divider()

    st.header("📅 Today's Report")
    if not df.empty:
        daily_df = df[df['Date'] == today_str]
    else:
        daily_df = pd.DataFrame(columns=df.columns)
        
    t_col1, t_col2 = st.columns(2)
    t_qty = daily_df['Qty'].sum() if not daily_df.empty else 0
    t_rev = daily_df['Total Price'].sum() if not daily_df.empty else 0.0
    
    t_col1.metric("Items Sold Today", int(t_qty))
    t_col2.metric("Revenue Today", f"₹{t_rev:.2f}")
    st.dataframe(daily_df.drop(columns=['hidden_id'], errors='ignore'), use_container_width=True, hide_index=True)

    st.divider()

    st.header("⏮️ Yesterday's Report")
    if not df.empty:
        yest_df = df[df['Date'] == yesterday_str]
    else:
        yest_df = pd.DataFrame(columns=df.columns)
        
    y_col1, y_col2 = st.columns(2)
    y_qty = yest_df['Qty'].sum() if not yest_df.empty else 0
    y_rev = yest_df['Total Price'].sum() if not yest_df.empty else 0.0
    
    y_col1.metric("Items Sold Yesterday", int(y_qty))
    y_col2.metric("Revenue Yesterday", f"₹{y_rev:.2f}")
    st.dataframe(yest_df.drop(columns=['hidden_id'], errors='ignore'), use_container_width=True, hide_index=True)

# --- TAB 2: ADD ENTRY ---
elif current_tab == "➕ Add Entry":
    st.header("New Sale")
    
    with st.form("add_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Item Name")
            # FIXED: Box empties on click, uses 1 if left blank
            qty = st.number_input("Quantity", min_value=1, value=None, placeholder="1")
            date_input = st.date_input("Date", datetime.today())
            date_str = date_input.strftime('%Y-%m-%d') 
            
        with col2:
            total_price = st.number_input("Total Price (₹)", min_value=0.0, value=None, placeholder="0.00")
            phone = st.text_input("Phone Number (Leave blank if paid)")
            
        submitted = st.form_submit_button("Save Entry", type="primary", use_container_width=True)
        
        if submitted:
            clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "")
            final_qty = qty if qty is not None else 1  # Treats empty qty as 1
            
            if not name:
                st.error("Item Name is required.")
            elif total_price is None:
                st.error("Please enter the Total Price.")
            elif clean_phone != "" and not clean_phone.isdigit():
                st.error("Invalid Phone Number: Please enter numbers only.")
            else:
                status = "Borrowed" if phone.strip() != "" else "Paid"
                
                new_row = {
                    'hidden_id': str(uuid.uuid4()), 
                    'Date': date_str, 
                    'Name': name, 
                    'Qty': final_qty, 
                    'Total Price': total_price, 
                    'Phone': phone, 
                    'Status': status
                }
                df = get_data()
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df)
                
                st.session_state.flash_success = f"Added {final_qty}x '{name}' successfully! Saved to Google Sheets."
                st.rerun()

# --- TAB 3: SEARCH ---
elif current_tab == "🔍 Search":
    st.header("Search Database")
    df = get_data()
    
    search_term = st.text_input("Type to search by Name, Date (YYYY-MM-DD), or Phone:")
    
    if search_term and not df.empty:
        mask = (
            df['Name'].astype(str).str.contains(search_term, case=False, na=False) | 
            df['Phone'].astype(str).str.contains(search_term, case=False, na=False) |
            df['Date'].astype(str).str.contains(search_term, case=False, na=False)
        )
        search_results = df[mask]
        
        if search_results.empty:
            st.warning("No entries found.")
        else:
            st.info(f"Found {len(search_results)} matching entries:")
            st.dataframe(search_results.drop(columns=['hidden_id'], errors='ignore'), use_container_width=True, hide_index=True)
    elif search_term and df.empty:
        st.warning("Database is empty.")

# --- TAB 4: EDIT / DELETE ---
elif current_tab == "✏️ Edit / Delete":
    st.header("Modify Database")
    df = get_data()
    
    if df.empty:
        st.warning("No data available to edit.")
    else:
        df_sorted = df.sort_values(by='Date', ascending=False)
        
        edit_options_dict = {f"{row['Date']} | {row['Name']} | Qty: {row['Qty']} | Phone: {row['Phone'] if str(row['Phone']).strip() != '' else 'N/A'}": row['hidden_id'] for _, row in df_sorted.iterrows()}
        
        selected_edit = st.selectbox(
            "Search or Select entry to modify:", 
            options=["-- Select an Entry --"] + list(edit_options_dict.keys())
        )
        
        if selected_edit != "-- Select an Entry --":
            target_id = edit_options_dict[selected_edit]
            row_data = df[df['hidden_id'] == target_id].iloc[0]
            
            with st.form("edit_delete_form"):
                st.write("### Edit Entry Details")
                new_name = st.text_input("Name", value=row_data['Name'])
                new_qty = st.number_input("Qty", min_value=1, value=int(row_data['Qty']))
                new_total = st.number_input("Total Price (₹)", min_value=0.0, value=float(row_data['Total Price']))
                new_phone = st.text_input("Phone", value=row_data['Phone'])
                new_date = st.text_input("Date (YYYY-MM-DD)", value=row_data['Date'])
                
                col1, col2 = st.columns(2)
                with col1:
                    update_btn = st.form_submit_button("Update Entry")
                with col2:
                    delete_btn = st.form_submit_button("Delete Entry", type="primary")
                    
                if update_btn:
                    clean_phone_edit = str(new_phone).replace(" ", "").replace("-", "").replace("+", "")
                    if clean_phone_edit != "" and not clean_phone_edit.isdigit():
                        st.error("Invalid Phone Number: Please enter numbers only.")
                    else:
                        df.loc[df['hidden_id'] == target_id, 'Name'] = new_name
                        df.loc[df['hidden_id'] == target_id, 'Qty'] = new_qty
                        df.loc[df['hidden_id'] == target_id, 'Total Price'] = new_total
                        df.loc[df['hidden_id'] == target_id, 'Phone'] = new_phone
                        df.loc[df['hidden_id'] == target_id, 'Date'] = new_date
                        df.loc[df['hidden_id'] == target_id, 'Status'] = 'Borrowed' if str(new_phone).strip() != "" else 'Paid'
                        
                        save_data(df)
                        st.session_state.flash_success = f"Entry for '{new_name}' updated in Google Sheets!"
                        st.rerun()
                    
                if delete_btn:
                    df = df[df['hidden_id'] != target_id]
                    save_data(df)
                    st.session_state.flash_error = "Entry permanently deleted from Google Sheets!"
                    st.rerun()
