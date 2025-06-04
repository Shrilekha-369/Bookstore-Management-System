import tkinter as tk
from tkinter import messagebox, ttk
import mysql.connector as mysqlcon
from datetime import datetime
import re
import logging
import hashlib
from decimal import Decimal
from typing import Optional, List, Tuple, Dict, Any

# Configure logging
logging.basicConfig(
    filename='bookstore.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def hash_password(password: str) -> str:
    """Generate SHA256 hash of a password"""
    return hashlib.sha256(password.encode()).hexdigest()

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()
        self.initialize_database()
        
    def connect(self):
        try:
            self.connection = mysqlcon.connect(
                host="localhost",
                user="root",
                password="password@123",
                database="ElDorado",
                autocommit=False
            )
            logging.info("Database connection established")
        except mysqlcon.Error as err:
            logging.error(f"Database connection failed: {err}")
            messagebox.showerror("Database Error", f"Failed to connect to database: {err}")
            raise

    def initialize_database(self):
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Staff(
                StaffID INT AUTO_INCREMENT PRIMARY KEY,
                Name VARCHAR(100) NOT NULL,
                Role ENUM('Manager', 'Clerk', 'Librarian') NOT NULL,
                Email VARCHAR(100) NOT NULL UNIQUE,
                Phone VARCHAR(15) NOT NULL UNIQUE,
                HireDate DATE DEFAULT (CURRENT_DATE),
                PasswordHash VARCHAR(255) NOT NULL
            )""")
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Books(
                BookID INT AUTO_INCREMENT PRIMARY KEY,
                BookName VARCHAR(500) NOT NULL,
                Genre VARCHAR(250) NOT NULL,
                Quantity INT NOT NULL CHECK (Quantity >= 0),
                Author VARCHAR(250) NOT NULL,
                Publisher VARCHAR(500) NOT NULL,
                Price DECIMAL(10,2) NOT NULL CHECK (Price >= 0),
                Update_by INT NOT NULL,
                LastUpdated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (Update_by) REFERENCES Staff(StaffID)
            )""")
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Accounts(
                CustomerID INT AUTO_INCREMENT PRIMARY KEY,
                CustomerName VARCHAR(50) NOT NULL,
                Phone VARCHAR(15) NOT NULL UNIQUE,
                Email VARCHAR(100) UNIQUE,
                Membership ENUM('Yes', 'No') DEFAULT 'No'
            )""")

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Orders(
                OrderID INT AUTO_INCREMENT PRIMARY KEY,
                CustomerID INT NOT NULL,
                StaffID INT NOT NULL,
                OrderDate DATETIME NOT NULL,
                TotalAmount DECIMAL(10,2) NOT NULL,
                Status ENUM('Pending', 'Completed', 'Cancelled') DEFAULT 'Pending',
                FOREIGN KEY (CustomerID) REFERENCES Accounts(CustomerID),
                FOREIGN KEY (StaffID) REFERENCES Staff(StaffID)
            )""")

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS OrderItems(
                OrderItemID INT AUTO_INCREMENT PRIMARY KEY,
                OrderID INT NOT NULL,
                BookID INT NOT NULL,
                Quantity INT NOT NULL,
                Price DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (OrderID) REFERENCES Orders(OrderID),
                FOREIGN KEY (BookID) REFERENCES Books(BookID)
            )""")

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS BookLog (
                LogID INT AUTO_INCREMENT PRIMARY KEY,
                BookID INT NOT NULL,
                Action ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
                ActionTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ActionBy INT NOT NULL,
                FOREIGN KEY (BookID) REFERENCES Books(BookID) ON DELETE CASCADE,
                FOREIGN KEY (ActionBy) REFERENCES Staff(StaffID)
            )""")

            triggers = {
                "AfterBookInsert": """
                CREATE TRIGGER AfterBookInsert
                AFTER INSERT ON Books
                FOR EACH ROW
                INSERT INTO BookLog(BookID, Action, ActionBy) VALUES (NEW.BookID, 'INSERT', NEW.Update_by)
                """,
                "AfterBookUpdate": """
                CREATE TRIGGER AfterBookUpdate
                AFTER UPDATE ON Books
                FOR EACH ROW
                INSERT INTO BookLog(BookID, Action, ActionBy) VALUES (NEW.BookID, 'UPDATE', NEW.Update_by)
                """,
                "BeforeBookDelete": """
                CREATE TRIGGER BeforeBookDelete
                BEFORE DELETE ON Books
                FOR EACH ROW
                BEGIN
                DECLARE manager_id INT;
                SET manager_id = (SELECT StaffID FROM Staff WHERE Role='Manager' LIMIT 1);
                IF manager_id IS NOT NULL THEN
                INSERT INTO BookLog(BookID, Action, ActionBy)
                VALUES (OLD.BookID, 'DELETE', manager_id);
                END IF;
                END
                """
            }

            for name, sql in triggers.items():
                cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
                cursor.execute(sql)
                logging.info(f"Trigger {name} created")

            # Add default admin if not exists
            cursor.execute("SELECT COUNT(*) FROM Staff WHERE Role='Manager'")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO Staff (Name, Role, Email, Phone, PasswordHash) "
                    "VALUES ('Admin', 'Manager', 'admin@eldorado.com', '0000000000', %s)",
                    (hash_password('admin123'),)
                )
                logging.info("Default admin account created")

            self.connection.commit()
            cursor.close()

        except mysqlcon.Error as err:
            self.connection.rollback()
            logging.error(f"Database initialization failed: {err}")
            messagebox.showerror("Database Error", f"Failed to initialize database: {err}")
            raise
            
    def execute_query(self, query: str, params: Tuple = None, fetch: bool = False) -> Optional[List[Tuple]]:
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params or ())
            if fetch:
                result = cursor.fetchall()
                cursor.close()
                return result
            else:
                self.connection.commit()
                cursor.close()
        except mysqlcon.Error as err:
            self.connection.rollback()
            logging.error(f"Query failed: {query} - Error: {err}")
            messagebox.showerror("Database Error", f"Operation failed: {err}")
            raise

    def close(self):
        if self.connection:
            self.connection.close()
            logging.info("Database connection closed")

class Validators:
    @staticmethod
    def validate_name(name: str) -> bool:
        return bool(re.fullmatch(r'^[A-Za-z\s]{2,50}$', name.strip()))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        return bool(re.fullmatch(r'^\+?\d{10,15}$', phone.strip()))
    
    @staticmethod
    def validate_email(email: str) -> bool:
        return bool(re.fullmatch(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email.strip()))
    
    @staticmethod
    def validate_price(price: str) -> bool:
        try:
            return float(price) >= 0
        except ValueError:
            return False
    
    @staticmethod
    def validate_quantity(quantity: str) -> bool:
        try:
            return int(quantity) > 0
        except ValueError:
            return False

class BookstoreApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.db = DatabaseManager()
        self.current_staff = None

        self.root.title("ElDorado Bookstore Management System")
        self.root.geometry("800x600")
        self.root.configure(bg='#f5f5f5')

        self.setup_styles()
        self.show_login_screen()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#f5f5f5')
        style.configure('TLabel', background='#f5f5f5', font=('Helvetica', 12))
        style.configure('Header.TLabel', font=('Helvetica', 18, 'bold'), foreground='#2c3e50')
        style.configure('TButton', font=('Helvetica', 11), padding=6)
        style.configure('Accent.TButton', font=('Helvetica', 11, 'bold'), foreground='white', background='#3498db')
        style.map('Accent.TButton', background=[('active', '#2980b9')])
        style.configure('Disabled.TButton', foreground='gray')

    def show_login_screen(self):
        self.login_window = tk.Toplevel(self.root)
        self.login_window.title("Staff Login")
        self.login_window.geometry("300x250")
        self.login_window.resizable(False, False)

        # Center the login window
        window_width = 300
        window_height = 250
        screen_width = self.login_window.winfo_screenwidth()
        screen_height = self.login_window.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.login_window.geometry(f"{window_width}x{window_height}+{x}+{y}")

        self.login_window.grab_set()
        self.login_window.focus_set()

        ttk.Label(
            self.login_window,
            text="ElDorado Bookstore",
            style='Header.TLabel'
        ).pack(pady=10)

        form_frame = ttk.Frame(self.login_window)
        form_frame.pack(pady=10, padx=20, fill='x')

        ttk.Label(form_frame, text="Email:").grid(row=0, column=0, pady=5, sticky='e')
        self.login_email = ttk.Entry(form_frame)
        self.login_email.grid(row=0, column=1, pady=5, sticky='ew')

        ttk.Label(form_frame, text="Password:").grid(row=1, column=0, pady=5, sticky='e')
        self.login_password = ttk.Entry(form_frame, show="*")
        self.login_password.grid(row=1, column=1, pady=5, sticky='ew')

        ttk.Button(
            self.login_window,
            text="Login",
            command=self.authenticate_staff,
            style='Accent.TButton'
        ).pack(pady=15)

        self.root.withdraw()

    def authenticate_staff(self):
        email = self.login_email.get().strip()
        password = self.login_password.get().strip()

        if not email or not password:
            messagebox.showerror("Error", "Please enter both email and password")
            return

        try:
            staff = self.db.execute_query(
                "SELECT StaffID, Name, Role, PasswordHash FROM Staff WHERE Email = %s",
                (email,),
                fetch=True
            )

            hashed_input = hash_password(password)

            if staff and staff[0][3] == hashed_input:
                self.current_staff = {
                    'id': staff[0][0],
                    'name': staff[0][1],
                    'role': staff[0][2]
                }
                self.login_window.destroy()
                self.setup_main_ui()
                self.root.deiconify()
            else:
                messagebox.showerror("Error", "Invalid credentials")

        except Exception as e:
            logging.error(f"Login failed: {e}")
            messagebox.showerror("Error", "Login failed")

    def setup_main_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        header_frame = ttk.Frame(self.root)
        header_frame.pack(pady=20, fill='x')

        ttk.Label(
            header_frame,
            text="ElDorado Bookstore",
            style='Header.TLabel'
        ).pack()

        ttk.Label(
            header_frame,
            text=f"Welcome, {self.current_staff['name']} ({self.current_staff['role']})",
            style='TLabel'
        ).pack()

        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20, padx=20, fill='both', expand=True)

        buttons = [
            ("📚 Book Management", self.book_management),
            ("👥 Customer Management", self.customer_management),
            ("🛒 Cart & Orders", self.order_management),
            ("👔 Staff Management", self.staff_management),
            ("📊 Reports", self.show_reports),
            ("⚙️ Settings", self.show_settings)
        ]

        for i, (text, command) in enumerate(buttons):
            btn = ttk.Button(
                button_frame,
                text=text,
                command=command,
                style='Accent.TButton' if i % 2 == 0 else 'TButton'
            )

            if text in ["👔 Staff Management", "📊 Reports"] and self.current_staff['role'] != 'Manager':
                btn.config(style='Disabled.TButton', state='disabled')

            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky='nsew')
            button_frame.grid_columnconfigure(i%2, weight=1)

        for row in range(3):
            button_frame.grid_rowconfigure(row, weight=1)

        self.status_var = tk.StringVar()
        self.status_var.set(f"Logged in as {self.current_staff['name']} | Role: {self.current_staff['role']}")

        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief='sunken',
            anchor='w'
        )
        status_bar.pack(side='bottom', fill='x')

    def book_management(self):
        window = tk.Toplevel(self.root)
        window.title("Book Management")
        window.geometry("900x600")

        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True)

        # Tab 1: Add Book
        add_frame = ttk.Frame(notebook)
        notebook.add(add_frame, text="➕ Add Book")

        fields = ["Book Name", "Genre", "Quantity", "Author", "Publisher", "Price"]
        self.add_entries = {}
        
        for i, label in enumerate(fields):
            ttk.Label(add_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
            entry = ttk.Entry(add_frame)
            entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
            self.add_entries[label] = entry

        ttk.Button(
            add_frame,
            text="Add Book",
            command=self.add_book,
            style='Accent.TButton'
        ).grid(row=len(fields), column=0, columnspan=2, pady=10)

        # Tab 2: Update Book
        update_frame = ttk.Frame(notebook)
        notebook.add(update_frame, text="✏️ Update Book")

        ttk.Label(update_frame, text="Select Book:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.update_book_combo = ttk.Combobox(update_frame, state="readonly")
        self.update_book_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')
        self.update_book_combo.bind("<<ComboboxSelected>>", self.load_book_details_for_update)

        self.update_entries = {}
        for i, label in enumerate(fields, start=1):
            ttk.Label(update_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
            entry = ttk.Entry(update_frame)
            entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
            self.update_entries[label] = entry

        ttk.Button(
            update_frame,
            text="Update Book",
            command=self.update_book,
            style='Accent.TButton'
        ).grid(row=len(fields)+1, column=0, columnspan=2, pady=10)

        # Tab 3: Delete Book
        delete_frame = ttk.Frame(notebook)
        notebook.add(delete_frame, text="🗑️ Delete Book")

        ttk.Label(delete_frame, text="Select Book:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.delete_book_combo = ttk.Combobox(delete_frame, state="readonly")
        self.delete_book_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')

        ttk.Button(
            delete_frame,
            text="Delete Book",
            command=self.delete_selected_book,
            style='Accent.TButton'
        ).grid(row=1, column=0, columnspan=2, pady=10)

        # Tab 4: View Books
        view_frame = ttk.Frame(notebook)
        notebook.add(view_frame, text="📖 View Books")

        columns = ("ID", "Book Name", "Genre", "Quantity", "Author", "Publisher", "Price", "Last Updated")
        self.books_tree = ttk.Treeview(view_frame, columns=columns, show='headings')
        
        for col in columns:
            self.books_tree.heading(col, text=col)
            self.books_tree.column(col, anchor='center', width=100)
        
        self.books_tree.column("Book Name", width=150)
        self.books_tree.column("Author", width=150)
        self.books_tree.column("Publisher", width=150)
        
        scrollbar = ttk.Scrollbar(view_frame, orient='vertical', command=self.books_tree.yview)
        self.books_tree.configure(yscrollcommand=scrollbar.set)
        
        self.books_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.populate_book_dropdowns()
        self.load_books()

    def populate_book_dropdowns(self):
        books = self.db.execute_query("SELECT BookID, BookName FROM Books", fetch=True)
        options = [f"{b[0]} - {b[1]}" for b in books]
        self.update_book_combo['values'] = options
        self.delete_book_combo['values'] = options

    def load_book_details_for_update(self, event):
        if not self.update_book_combo.get(): 
            return
            
        book_id = self.update_book_combo.get().split(' - ')[0]
        book = self.db.execute_query(
            "SELECT BookName, Genre, Quantity, Author, Publisher, Price FROM Books WHERE BookID=%s", 
            (book_id,), 
            fetch=True
        )
        
        if book:
            values = book[0]
            for key, val in zip(self.update_entries.keys(), values):
                self.update_entries[key].delete(0, 'end')
                self.update_entries[key].insert(0, str(val))
            self.selected_update_book_id = book_id

    def delete_selected_book(self):
        if not self.delete_book_combo.get(): 
            return
            
        book_id = self.delete_book_combo.get().split(' - ')[0]
        book_name = self.delete_book_combo.get().split(' - ')[1]
        
        if not messagebox.askyesno("Confirm", f"Delete book '{book_name}'?"):
            return
            
        try:
            manager_exists = self.db.execute_query(
                "SELECT StaffID FROM Staff WHERE Role='Manager' LIMIT 1",
                fetch=True
            )
            if not manager_exists:
                messagebox.showerror("Error", "Cannot delete book — no manager exists for logging.")
                return
            
            self.db.execute_query("DELETE FROM Books WHERE BookID = %s", (book_id,))
            messagebox.showinfo("Success", "Book deleted successfully!")
            self.load_books()
            self.populate_book_dropdowns()
        except Exception as e:
            logging.error(f"Delete book failed: {e}")
            messagebox.showerror("Error", f"Failed to delete: {e}")

    def add_book(self):
        try:
            # Get all field values
            book_name = self.add_entries["Book Name"].get().strip()
            genre = self.add_entries["Genre"].get().strip()
            quantity = self.add_entries["Quantity"].get().strip()
            author = self.add_entries["Author"].get().strip()
            publisher = self.add_entries["Publisher"].get().strip()
            price = self.add_entries["Price"].get().strip()

            # Validate inputs
            if not all([book_name, genre, author, publisher]):
                messagebox.showerror("Error", "Please fill all text fields")
                return
                
            if not Validators.validate_quantity(quantity):
                messagebox.showerror("Error", "Invalid quantity")
                return
                
            if not Validators.validate_price(price):
                messagebox.showerror("Error", "Invalid price")
                return
            staff_check = self.db.execute_query(
                "SELECT 1 FROM Staff WHERE StaffID = %s",
                (self.current_staff['id'],),
                fetch=True
            )
            if not staff_check:
                messagebox.showerror("Error", "Current staff ID is invalid or deleted")
                return
            
            # Insert into database
            self.db.execute_query(
                "INSERT INTO Books (BookName, Genre, Quantity, Author, Publisher, Price, Update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (book_name, genre, int(quantity), author, publisher, float(price), self.current_staff['id'])
            )
            
            messagebox.showinfo("Success", "Book added successfully!")
            
            # Clear form and refresh data
            for entry in self.add_entries.values():
                entry.delete(0, 'end')
                
            self.load_books()
            self.populate_book_dropdowns()
            
        except Exception as e:
            logging.error(f"Add book failed: {e}")
            messagebox.showerror("Error", f"Failed to add book: {e}")

    def update_book(self):
        try:
            if not hasattr(self, 'selected_update_book_id'):
                messagebox.showerror("Error", "No book selected")
                return
                
            # Get all field values
            book_name = self.update_entries["Book Name"].get().strip()
            genre = self.update_entries["Genre"].get().strip()
            quantity = self.update_entries["Quantity"].get().strip()
            author = self.update_entries["Author"].get().strip()
            publisher = self.update_entries["Publisher"].get().strip()
            price = self.update_entries["Price"].get().strip()

            # Validate inputs
            if not all([book_name, genre, author, publisher]):
                messagebox.showerror("Error", "Please fill all text fields")
                return
                
            if not Validators.validate_quantity(quantity):
                messagebox.showerror("Error", "Invalid quantity")
                return
                
            if not Validators.validate_price(price):
                messagebox.showerror("Error", "Invalid price")
                return

            # Update database
            self.db.execute_query(
                "UPDATE Books SET BookName=%s, Genre=%s, Quantity=%s, Author=%s, Publisher=%s, Price=%s, Update_by=%s "
                "WHERE BookID=%s",
                (book_name, genre, int(quantity), author, publisher, float(price), self.current_staff['id'], self.selected_update_book_id)
            )
            
            messagebox.showinfo("Success", "Book updated successfully!")
            
            # Clear form and refresh data
            for entry in self.update_entries.values():
                entry.delete(0, 'end')
                
            self.load_books()
            self.populate_book_dropdowns()
            
        except Exception as e:
            logging.error(f"Update book failed: {e}")
            messagebox.showerror("Error", f"Failed to update book: {e}")

    def load_books(self):
        for item in self.books_tree.get_children():
            self.books_tree.delete(item)
            
        books = self.db.execute_query(
            "SELECT BookID, BookName, Genre, Quantity, Author, Publisher, Price, LastUpdated FROM Books",
            fetch=True
        )
        
        for book in books:
            self.books_tree.insert('', 'end', values=book)

    def customer_management(self):
        window = tk.Toplevel(self.root)
        window.title("Customer Management")
        window.geometry("800x600")

        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True)

        # Tab 1: Add Customer
        add_frame = ttk.Frame(notebook)
        notebook.add(add_frame, text="➕ Add Customer")

        fields = ["Customer Name", "Phone", "Email", "Membership"]
        self.customer_add_entries = {}
        
        for i, label in enumerate(fields):
            ttk.Label(add_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
            
            if label == "Membership":
                var = tk.StringVar(value="No")
                cb = ttk.Combobox(add_frame, textvariable=var, values=["Yes", "No"], state="readonly")
                cb.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                self.customer_add_entries[label] = var
            else:
                entry = ttk.Entry(add_frame)
                entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                self.customer_add_entries[label] = entry

        ttk.Button(
            add_frame,
            text="Add Customer",
            command=self.add_customer,
            style='Accent.TButton'
        ).grid(row=len(fields), column=0, columnspan=2, pady=10)

        # Tab 2: Update Customer
        update_frame = ttk.Frame(notebook)
        notebook.add(update_frame, text="✏️ Update Customer")

        ttk.Label(update_frame, text="Select Customer:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.update_customer_combo = ttk.Combobox(update_frame, state="readonly")
        self.update_customer_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')
        self.update_customer_combo.bind("<<ComboboxSelected>>", self.load_customer_details_for_update)

        self.customer_update_entries = {}
        for i, label in enumerate(fields, start=1):
            ttk.Label(update_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
            
            if label == "Membership":
                var = tk.StringVar()
                cb = ttk.Combobox(update_frame, textvariable=var, values=["Yes", "No"], state="readonly")
                cb.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                self.customer_update_entries[label] = var
            else:
                entry = ttk.Entry(update_frame)
                entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                self.customer_update_entries[label] = entry

        ttk.Button(
            update_frame,
            text="Update Customer",
            command=self.update_customer,
            style='Accent.TButton'
        ).grid(row=len(fields)+1, column=0, columnspan=2, pady=10)

        # Tab 3: Delete Customer
        delete_frame = ttk.Frame(notebook)
        notebook.add(delete_frame, text="🗑️ Delete Customer")

        ttk.Label(delete_frame, text="Select Customer:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.delete_customer_combo = ttk.Combobox(delete_frame, state="readonly")
        self.delete_customer_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')

        ttk.Button(
            delete_frame,
            text="Delete Customer",
            command=self.delete_selected_customer,
            style='Accent.TButton'
        ).grid(row=1, column=0, columnspan=2, pady=10)

        # Tab 4: View Customers
        view_frame = ttk.Frame(notebook)
        notebook.add(view_frame, text="👥 View Customers")

        columns = ("ID", "Name", "Phone", "Email", "Membership")
        self.customers_tree = ttk.Treeview(view_frame, columns=columns, show='headings')
        
        for col in columns:
            self.customers_tree.heading(col, text=col)
            self.customers_tree.column(col, anchor='center', width=100)
        
        self.customers_tree.column("Name", width=150)
        self.customers_tree.column("Email", width=200)
        
        scrollbar = ttk.Scrollbar(view_frame, orient='vertical', command=self.customers_tree.yview)
        self.customers_tree.configure(yscrollcommand=scrollbar.set)
        
        self.customers_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.populate_customer_dropdowns()
        self.load_customers()

    def populate_customer_dropdowns(self):
        customers = self.db.execute_query("SELECT CustomerID, CustomerName FROM Accounts", fetch=True)
        options = [f"{c[0]} - {c[1]}" for c in customers]
        self.update_customer_combo['values'] = options
        self.delete_customer_combo['values'] = options

    def load_customer_details_for_update(self, event):
        if not self.update_customer_combo.get(): 
            return
            
        customer_id = self.update_customer_combo.get().split(' - ')[0]
        customer = self.db.execute_query(
            "SELECT CustomerName, Phone, Email, Membership FROM Accounts WHERE CustomerID=%s", 
            (customer_id,), 
            fetch=True
        )
        
        if customer:
            name, phone, email, membership = customer[0]
            self.customer_update_entries["Customer Name"].delete(0, 'end')
            self.customer_update_entries["Customer Name"].insert(0, name)
            self.customer_update_entries["Phone"].delete(0, 'end')
            self.customer_update_entries["Phone"].insert(0, phone)
            self.customer_update_entries["Email"].delete(0, 'end')
            self.customer_update_entries["Email"].insert(0, email)
            self.customer_update_entries["Membership"].set(membership)
            self.selected_update_customer_id = customer_id

    def delete_selected_customer(self):
        if not self.delete_customer_combo.get(): 
            return
            
        customer_id = self.delete_customer_combo.get().split(' - ')[0]
        customer_name = self.delete_customer_combo.get().split(' - ')[1]
        
        if not messagebox.askyesno("Confirm", f"Delete customer '{customer_name}'?"):
            return
            
        try:
            # Check if customer has any orders
            orders = self.db.execute_query(
                "SELECT COUNT(*) FROM Orders WHERE CustomerID=%s",
                (customer_id,),
                fetch=True
            )
            
            if orders and orders[0][0] > 0:
                messagebox.showerror("Error", "Cannot delete customer with existing orders")
                return
                
            self.db.execute_query("DELETE FROM Accounts WHERE CustomerID = %s", (customer_id,))
            messagebox.showinfo("Success", "Customer deleted successfully!")
            self.load_customers()
            self.populate_customer_dropdowns()
        except Exception as e:
            logging.error(f"Delete customer failed: {e}")
            messagebox.showerror("Error", f"Failed to delete: {e}")

    def add_customer(self):
        try:
            # Get all field values
            name = self.customer_add_entries["Customer Name"].get().strip()
            phone = self.customer_add_entries["Phone"].get().strip()
            email = self.customer_add_entries["Email"].get().strip()
            membership = self.customer_add_entries["Membership"].get()

            # Validate inputs
            if not all([name, phone, email]):
                messagebox.showerror("Error", "Please fill all required fields")
                return
                
            if not Validators.validate_name(name):
                messagebox.showerror("Error", "Invalid name")
                return
                
            if not Validators.validate_phone(phone):
                messagebox.showerror("Error", "Invalid phone number")
                return
                
            if not Validators.validate_email(email):
                messagebox.showerror("Error", "Invalid email")
                return

            # Insert into database
            self.db.execute_query(
                "INSERT INTO Accounts (CustomerName, Phone, Email, Membership) "
                "VALUES (%s, %s, %s, %s)",
                (name, phone, email, membership)
            )
            
            messagebox.showinfo("Success", "Customer added successfully!")
            
            # Clear form and refresh data
            for entry in self.customer_add_entries.values():
                if isinstance(entry, tk.Entry):
                    entry.delete(0, 'end')
                else:
                    entry.set("No")
                
            self.load_customers()
            self.populate_customer_dropdowns()
            
        except mysqlcon.IntegrityError as e:
            if "Duplicate entry" in str(e):
                messagebox.showerror("Error", "Phone number or email already exists")
            else:
                messagebox.showerror("Error", f"Database error: {e}")
            logging.error(f"Add customer failed: {e}")
        except Exception as e:
            logging.error(f"Add customer failed: {e}")
            messagebox.showerror("Error", f"Failed to add customer: {e}")

    def update_customer(self):
        try:
            if not hasattr(self, 'selected_update_customer_id'):
                messagebox.showerror("Error", "No customer selected")
                return
                
            # Get all field values
            name = self.customer_update_entries["Customer Name"].get().strip()
            phone = self.customer_update_entries["Phone"].get().strip()
            email = self.customer_update_entries["Email"].get().strip()
            membership = self.customer_update_entries["Membership"].get()

            # Validate inputs
            if not all([name, phone, email]):
                messagebox.showerror("Error", "Please fill all required fields")
                return
                
            if not Validators.validate_name(name):
                messagebox.showerror("Error", "Invalid name")
                return
                
            if not Validators.validate_phone(phone):
                messagebox.showerror("Error", "Invalid phone number")
                return
                
            if not Validators.validate_email(email):
                messagebox.showerror("Error", "Invalid email")
                return

            # Update database
            self.db.execute_query(
                "UPDATE Accounts SET CustomerName=%s, Phone=%s, Email=%s, Membership=%s "
                "WHERE CustomerID=%s",
                (name, phone, email, membership, self.selected_update_customer_id)
            )
            
            messagebox.showinfo("Success", "Customer updated successfully!")
            
            # Clear form and refresh data
            for entry in self.customer_update_entries.values():
                if isinstance(entry, tk.Entry):
                    entry.delete(0, 'end')
                else:
                    entry.set("No")
                
            self.load_customers()
            self.populate_customer_dropdowns()
            
        except mysqlcon.IntegrityError as e:
            if "Duplicate entry" in str(e):
                messagebox.showerror("Error", "Phone number or email already exists")
            else:
                messagebox.showerror("Error", f"Database error: {e}")
            logging.error(f"Update customer failed: {e}")
        except Exception as e:
            logging.error(f"Update customer failed: {e}")
            messagebox.showerror("Error", f"Failed to update customer: {e}")

    def load_customers(self):
        for item in self.customers_tree.get_children():
            self.customers_tree.delete(item)
            
        customers = self.db.execute_query(
            "SELECT CustomerID, CustomerName, Phone, Email, Membership FROM Accounts",
            fetch=True
        )
        
        for customer in customers:
            self.customers_tree.insert('', 'end', values=customer)
    def staff_management(self):
        window = tk.Toplevel(self.root)
        window.title("Staff Management")
        window.geometry("800x600")

        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True)

        # Tab 1: View Staff (for all roles)
        view_frame = ttk.Frame(notebook)
        notebook.add(view_frame, text="👥 View Staff")

        columns = ("ID", "Name", "Role", "Phone", "Email")
        self.staff_tree = ttk.Treeview(view_frame, columns=columns, show='headings')
        
        for col in columns:
            self.staff_tree.heading(col, text=col)
            self.staff_tree.column(col, anchor='center', width=100)
        
        self.staff_tree.column("Name", width=150)
        self.staff_tree.column("Email", width=200)
        
        scrollbar = ttk.Scrollbar(view_frame, orient='vertical', command=self.staff_tree.yview)
        self.staff_tree.configure(yscrollcommand=scrollbar.set)
        
        self.staff_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Only show management tabs if user is a manager
        if self.current_staff['role'] == 'Manager':
            # Tab 2: Add Staff
            add_frame = ttk.Frame(notebook)
            notebook.add(add_frame, text="➕ Add Staff")

            fields = [
                ("Name", "staff_name"),
                ("Role", "staff_role"),
                ("Phone", "staff_phone"),
                ("Email", "staff_email"),
                ("Password", "staff_password")
            ]

            for i, (label, var_name) in enumerate(fields):
                ttk.Label(add_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
                
                if label == "Role":
                    var = tk.StringVar()
                    cb = ttk.Combobox(add_frame, textvariable=var, values=["Manager", "Clerk", "Librarian"], state="readonly")
                    cb.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                    setattr(self, var_name, var)
                else:
                    entry = ttk.Entry(add_frame)
                    if label == "Password":
                        entry.config(show="*")
                    entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                    setattr(self, var_name, entry)

            ttk.Button(
                add_frame,
                text="Add Staff",
                command=self.add_staff,
                style='Accent.TButton'
            ).grid(row=len(fields), column=0, columnspan=2, pady=10)

            # Tab 3: Update/Delete Staff
            manage_frame = ttk.Frame(notebook)
            notebook.add(manage_frame, text="✏️ Manage Staff")

            ttk.Label(manage_frame, text="Select Staff:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
            self.staff_combo = ttk.Combobox(manage_frame, state="readonly")
            self.staff_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')
            self.staff_combo.bind("<<ComboboxSelected>>", self.load_staff_details)

            self.manage_entries = {}
            for i, (label, var_name) in enumerate(fields, start=1):
                ttk.Label(manage_frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky='e')
                
                if label == "Role":
                    var = tk.StringVar()
                    cb = ttk.Combobox(manage_frame, textvariable=var, values=["Manager", "Clerk", "Librarian"], state="readonly")
                    cb.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                    self.manage_entries[var_name] = var
                else:
                    entry = ttk.Entry(manage_frame)
                    if label == "Password":
                        entry.config(show="*")
                    entry.grid(row=i, column=1, padx=10, pady=5, sticky='ew')
                    self.manage_entries[var_name] = entry

            button_frame = ttk.Frame(manage_frame)
            button_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=10)

            ttk.Button(
                button_frame,
                text="Update Staff",
                command=self.update_staff,
                style='Accent.TButton'
            ).pack(side='left', padx=5)

            ttk.Button(
                button_frame,
                text="Delete Staff",
                command=self.delete_staff
            ).pack(side='left', padx=5)

            # Populate staff dropdown for managers
            self.populate_staff_dropdowns()

        # Load staff list for all users
        self.load_staff_list()            
    def populate_staff_dropdowns(self):
        staff = self.db.execute_query("SELECT StaffID, Name FROM Staff", fetch=True)
        options = [f"{s[0]} - {s[1]}" for s in staff]
        self.staff_combo['values'] = options

    def load_staff_details(self, event):
        if not self.staff_combo.get(): 
            return
            
        staff_id = self.staff_combo.get().split(' - ')[0]
        staff = self.db.execute_query(
            "SELECT Name, Role, Phone, Email FROM Staff WHERE StaffID=%s", 
            (staff_id,), 
            fetch=True
        )
        
        if staff:
            name, role, phone, email = staff[0]
            self.manage_entries["staff_name"].delete(0, 'end')
            self.manage_entries["staff_name"].insert(0, name)
            self.manage_entries["staff_role"].set(role)
            self.manage_entries["staff_phone"].delete(0, 'end')
            self.manage_entries["staff_phone"].insert(0, phone)
            self.manage_entries["staff_email"].delete(0, 'end')
            self.manage_entries["staff_email"].insert(0, email)
            self.manage_entries["staff_password"].delete(0, 'end')
            self.selected_staff_id = staff_id

    def add_staff(self):
        try:
            # Get all field values
            name = self.staff_name.get().strip()
            role = self.staff_role.get().strip()
            phone = self.staff_phone.get().strip()
            email = self.staff_email.get().strip()
            password = self.staff_password.get().strip()

            # Validate inputs
            if not all([name, role, phone, email, password]):
                messagebox.showerror("Error", "Please fill all fields")
                return
                
            if not Validators.validate_name(name):
                messagebox.showerror("Error", "Invalid name")
                return
                
            if not Validators.validate_phone(phone):
                messagebox.showerror("Error", "Invalid phone number")
                return
                
            if not Validators.validate_email(email):
                messagebox.showerror("Error", "Invalid email")
                return

            # Hash password
            password_hash = hash_password(password)

            # Insert into database
            self.db.execute_query(
                "INSERT INTO Staff (Name, Role, Phone, Email, PasswordHash) "
                "VALUES (%s, %s, %s, %s, %s)",
                (name, role, phone, email, password_hash))
            
            messagebox.showinfo("Success", "Staff member added successfully!")
            
            # Clear form and refresh data
            self.staff_name.delete(0, 'end')
            self.staff_role.set('')
            self.staff_phone.delete(0, 'end')
            self.staff_email.delete(0, 'end')
            self.staff_password.delete(0, 'end')
                
            self.populate_staff_dropdowns()
            self.load_staff_list()
            
        except Exception as e:
            logging.error(f"Add staff failed: {e}")
            messagebox.showerror("Error", f"Failed to add staff: {e}")

    def update_staff(self):
        try:
            if not hasattr(self, 'selected_staff_id'):
                messagebox.showerror("Error", "No staff member selected")
                return
                
            # Get all field values
            name = self.manage_entries["staff_name"].get().strip()
            role = self.manage_entries["staff_role"].get().strip()
            phone = self.manage_entries["staff_phone"].get().strip()
            email = self.manage_entries["staff_email"].get().strip()
            password = self.manage_entries["staff_password"].get().strip()

            # Validate inputs
            if not all([name, role, phone, email]):
                messagebox.showerror("Error", "Please fill all required fields")
                return
                
            if not Validators.validate_name(name):
                messagebox.showerror("Error", "Invalid name")
                return
                
            if not Validators.validate_phone(phone):
                messagebox.showerror("Error", "Invalid phone number")
                return
                
            if not Validators.validate_email(email):
                messagebox.showerror("Error", "Invalid email")
                return

            # Update database
            if password:
                password_hash = hash_password(password)
                self.db.execute_query(
                    "UPDATE Staff SET Name=%s, Role=%s, Phone=%s, Email=%s, PasswordHash=%s "
                    "WHERE StaffID=%s",
                    (name, role, phone, email, password_hash, self.selected_staff_id)
                )
            else:
                self.db.execute_query(
                    "UPDATE Staff SET Name=%s, Role=%s, Phone=%s, Email=%s "
                    "WHERE StaffID=%s",
                    (name, role, phone, email, self.selected_staff_id)
                )
            
            messagebox.showinfo("Success", "Staff member updated successfully!")
            
            # Clear form and refresh data
            for entry in self.manage_entries.values():
                if isinstance(entry, tk.Entry):
                    entry.delete(0, 'end')
                else:
                    entry.set('')
                
            self.populate_staff_dropdowns()
            self.load_staff_list()
            
        except Exception as e:
            logging.error(f"Update staff failed: {e}")
            messagebox.showerror("Error", f"Failed to update staff: {e}")

    def delete_staff(self):
        try:
            if not hasattr(self, 'selected_staff_id'):
                messagebox.showerror("Error", "No staff member selected")
                return
                
            staff_id = self.selected_staff_id
            staff_name = self.manage_entries["staff_name"].get().strip()
            
            if not messagebox.askyesno("Confirm", f"Delete staff member '{staff_name}'?"):
                return
                
            # Don't allow deletion of the last manager
            if self.current_staff['id'] == int(staff_id):
                messagebox.showerror("Error", "Cannot delete currently logged in staff")
                return
                
            # Check if this is the last manager
            staff = self.db.execute_query(
                "SELECT Role FROM Staff WHERE StaffID=%s", 
                (staff_id,), 
                fetch=True
            )
            
            if staff and staff[0][0] == 'Manager':
                managers = self.db.execute_query(
                    "SELECT COUNT(*) FROM Staff WHERE Role='Manager'", 
                    fetch=True
                )
                if managers and managers[0][0] <= 1:
                    messagebox.showerror("Error", "Cannot delete the last manager")
                    return

            # Delete from database
            self.db.execute_query("DELETE FROM Staff WHERE StaffID = %s", (staff_id,))
            
            messagebox.showinfo("Success", "Staff member deleted successfully!")
            
            # Clear form and refresh data
            for entry in self.manage_entries.values():
                if isinstance(entry, tk.Entry):
                    entry.delete(0, 'end')
                else:
                    entry.set('')
                
            self.populate_staff_dropdowns()
            self.load_staff_list()
            
        except Exception as e:
            logging.error(f"Delete staff failed: {e}")
            messagebox.showerror("Error", f"Failed to delete staff: {e}")

    def load_staff_list(self):
        for item in self.staff_tree.get_children():
            self.staff_tree.delete(item)
            
        staff = self.db.execute_query(
            "SELECT StaffID, Name, Role, Phone, Email FROM Staff",
            fetch=True
        )
        
        for member in staff:
            self.staff_tree.insert('', 'end', values=member)

    def order_management(self):
        window = tk.Toplevel(self.root)
        window.title("Order Management")
        window.geometry("1000x700")

        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True)

        # Tab 1: Create New Order
        create_frame = ttk.Frame(notebook)
        notebook.add(create_frame, text="🛒 Create Order")

        # Customer selection
        ttk.Label(create_frame, text="Customer:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.customer_combobox = ttk.Combobox(create_frame, state="readonly")
        self.customer_combobox.grid(row=0, column=1, padx=10, pady=5, sticky='ew')

        # Load customers into combobox
        self.populate_customer_combobox()

        # Book selection and cart management
        ttk.Label(create_frame, text="Add to Cart:").grid(row=1, column=0, padx=10, pady=5, sticky='e')

        book_frame = ttk.Frame(create_frame)
        book_frame.grid(row=1, column=1, padx=10, pady=5, sticky='ew')

        ttk.Label(book_frame, text="Book:").pack(side='left')
        self.book_combobox = ttk.Combobox(book_frame, state="readonly")
        self.book_combobox.pack(side='left', padx=5, expand=True, fill='x')

        ttk.Label(book_frame, text="Qty:").pack(side='left', padx=(10, 5))
        self.order_qty = ttk.Spinbox(book_frame, from_=1, to=100, width=5)
        self.order_qty.pack(side='left')

        ttk.Button(
            book_frame,
            text="Add",
            command=self.add_to_cart,
            style='Accent.TButton'
        ).pack(side='left', padx=5)

        # Load books into combobox
        self.populate_book_combobox()

        # Cart display
        ttk.Label(create_frame, text="Cart Items:").grid(row=2, column=0, padx=10, pady=5, sticky='ne')

        cart_frame = ttk.Frame(create_frame)
        cart_frame.grid(row=2, column=1, padx=10, pady=5, sticky='nsew')

        columns = ("Book ID", "Book Name", "Quantity", "Price", "Subtotal")
        self.cart_tree = ttk.Treeview(
            cart_frame,
            columns=columns,
            show='headings',
            height=5
        )

        for col in columns:
            self.cart_tree.heading(col, text=col)
            self.cart_tree.column(col, width=80, anchor='center')

        self.cart_tree.column("Book Name", width=200)

        scrollbar = ttk.Scrollbar(cart_frame, orient='vertical', command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=scrollbar.set)

        self.cart_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Order summary
        summary_frame = ttk.Frame(create_frame)
        summary_frame.grid(row=3, column=1, padx=10, pady=10, sticky='e')

        ttk.Label(summary_frame, text="Total Items:").grid(row=0, column=0, sticky='e')
        self.total_items_var = tk.StringVar(value="0")
        ttk.Label(summary_frame, textvariable=self.total_items_var).grid(row=0, column=1, sticky='w', padx=5)

        ttk.Label(summary_frame, text="Total Amount:").grid(row=1, column=0, sticky='e')
        self.total_amount_var = tk.StringVar(value="$0.00")
        ttk.Label(summary_frame, textvariable=self.total_amount_var).grid(row=1, column=1, sticky='w', padx=5)

        # Action buttons
        button_frame = ttk.Frame(create_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(
            button_frame,
            text="Place Order",
            command=lambda: self.place_order(status="Completed"),
            style='Accent.TButton'
        ).pack(side='left', padx=5)

        ttk.Button(
            button_frame,
            text="Save as Pending",
            command=lambda: self.place_order(status="Pending"),
            style='TButton'
        ).pack(side='left', padx=5)

        ttk.Button(
            button_frame,
            text="Clear Cart",
            command=self.clear_cart
        ).pack(side='left', padx=5)

        # Tab 2: Manage Pending Orders
        pending_frame = ttk.Frame(notebook)
        notebook.add(pending_frame, text="⏳ Pending Orders")

        # Pending orders treeview
        columns = ("Order ID", "Customer", "Date", "Total", "Status")
        self.pending_orders_tree = ttk.Treeview(
            pending_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )

        for col in columns:
            self.pending_orders_tree.heading(col, text=col)
            self.pending_orders_tree.column(col, width=100, anchor='center')

        self.pending_orders_tree.column("Customer", width=150)
        self.pending_orders_tree.column("Date", width=120)

        scrollbar = ttk.Scrollbar(pending_frame, orient='vertical', command=self.pending_orders_tree.yview)
        self.pending_orders_tree.configure(yscrollcommand=scrollbar.set)

        self.pending_orders_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Order items frame
        items_frame = ttk.Frame(pending_frame)
        items_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(items_frame, text="Order Items:").pack(anchor='w')
        
        columns = ("Book ID", "Book Name", "Quantity", "Price", "Subtotal")
        self.pending_items_tree = ttk.Treeview(
            items_frame,
            columns=columns,
            show='headings',
            height=5
        )

        for col in columns:
            self.pending_items_tree.heading(col, text=col)
            self.pending_items_tree.column(col, width=80, anchor='center')

        self.pending_items_tree.column("Book Name", width=200)

        scrollbar = ttk.Scrollbar(items_frame, orient='vertical', command=self.pending_items_tree.yview)
        self.pending_items_tree.configure(yscrollcommand=scrollbar.set)

        self.pending_items_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Action buttons for pending orders
        action_frame = ttk.Frame(pending_frame)
        action_frame.pack(fill='x', padx=10, pady=10)

        ttk.Button(
            action_frame,
            text="Complete Order",
            command=lambda: self.update_order_status("Completed"),
            style='Accent.TButton'
        ).pack(side='left', padx=5)

        ttk.Button(
            action_frame,
            text="Cancel Order",
            command=lambda: self.update_order_status("Cancelled"),
            style='TButton'
        ).pack(side='left', padx=5)

        ttk.Button(
            action_frame,
            text="Refresh",
            command=self.load_pending_orders
        ).pack(side='right', padx=5)

        # Tab 3: View All Orders
        view_frame = ttk.Frame(notebook)
        notebook.add(view_frame, text="📋 Order History")

        # Order treeview
        columns = ("Order ID", "Customer", "Date", "Total", "Status")
        self.orders_tree = ttk.Treeview(
            view_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )

        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=100, anchor='center')

        self.orders_tree.column("Customer", width=150)
        self.orders_tree.column("Date", width=120)

        scrollbar = ttk.Scrollbar(view_frame, orient='vertical', command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)

        self.orders_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Load initial data
        self.load_pending_orders()
        self.load_order_history()

        # Configure grid weights
        create_frame.grid_columnconfigure(1, weight=1)
        create_frame.grid_rowconfigure(2, weight=1)

    def populate_customer_combobox(self):
        customers = self.db.execute_query(
            "SELECT CustomerID, CustomerName FROM Accounts",
            fetch=True
        )
        self.customer_combobox['values'] = [f"{cid} - {name}" for cid, name in customers]

    def populate_book_combobox(self):
        books = self.db.execute_query(
            "SELECT BookID, BookName FROM Books WHERE Quantity > 0",
            fetch=True
        )
        self.book_combobox['values'] = [f"{bid} - {name}" for bid, name in books]

    def add_to_cart(self):
        """Add selected book to the cart"""
        try:
            # Get selected book
            book_selection = self.book_combobox.get()
            if not book_selection:
                messagebox.showerror("Error", "Please select a book")
                return
            
            book_id = int(book_selection.split(" - ")[0])
            quantity = int(self.order_qty.get())
            
            if quantity <= 0:
                messagebox.showerror("Error", "Quantity must be positive")
                return
            
            # Get book details
            book = self.db.execute_query(
                "SELECT BookName, Price, Quantity FROM Books WHERE BookID=%s",
                (book_id,),
                fetch=True
            )
            
            if not book:
                messagebox.showerror("Error", "Book not found")
                return
            
            book_name, price, available_qty = book[0]
            
            if quantity > available_qty:
                messagebox.showerror("Error", f"Only {available_qty} available in stock")
                return
            
            # Add to cart treeview
            subtotal = price * quantity
            self.cart_tree.insert('', 'end', values=(book_id, book_name, quantity, f"${price:.2f}", f"${subtotal:.2f}"))
            
            # Update totals
            self.update_order_totals()
            
            # Clear selection
            self.book_combobox.set('')
            self.order_qty.delete(0, 'end')
            self.order_qty.insert(0, '1')
        
        except Exception as e:
            logging.error(f"Error adding to cart: {e}")
            messagebox.showerror("Error", f"Failed to add to cart: {e}")

    def update_order_totals(self):
        """Update the order summary totals"""
        total_items = 0
        total_amount = 0.0
        
        for item in self.cart_tree.get_children():
            values = self.cart_tree.item(item)['values']
            total_items += int(values[2])
            total_amount += float(values[4][1:])  # Remove $ sign
        
        self.total_items_var.set(str(total_items))
        self.total_amount_var.set(f"${total_amount:.2f}")

    def clear_cart(self):
        """Clear all items from the cart"""
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        
        self.total_items_var.set("0")
        self.total_amount_var.set("$0.00")

    def place_order(self, status="Completed"):
        """Place the order and save to database"""
        try:
            # Validate customer selection
            customer_selection = self.customer_combobox.get()
            if not customer_selection:
                messagebox.showerror("Error", "Please select a customer")
                return
            
            customer_id = int(customer_selection.split(" - ")[0])
            
            # Validate cart has items
            cart_items = self.cart_tree.get_children()
            if not cart_items:
                messagebox.showerror("Error", "Cart is empty")
                return
            
            # Calculate total amount
            total_amount = sum(
                float(self.cart_tree.item(item)['values'][4][1:])  # Remove $ sign
                for item in cart_items
            )
            
            # Start transaction
            self.db.connection.start_transaction()
            
            # Create order record
            order_date = datetime.now()
            cursor = self.db.connection.cursor()
            
            cursor.execute(
                "INSERT INTO Orders (CustomerID, StaffID, OrderDate, TotalAmount, Status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (customer_id, self.current_staff['id'], order_date, total_amount, status)
            )
            
            order_id = cursor.lastrowid
            
            # Add order items and update book quantities (if order is completed)
            for item in cart_items:
                values = self.cart_tree.item(item)['values']
                book_id = values[0]
                quantity = values[2]
                price = float(values[3][1:])  # Remove $ sign
                
                # Add order item
                cursor.execute(
                    "INSERT INTO OrderItems (OrderID, BookID, Quantity, Price) "
                    "VALUES (%s, %s, %s, %s)",
                    (order_id, book_id, quantity, price)
                )
                
                # Update book quantity if order is completed
                if status == "Completed":
                    cursor.execute(
                        "UPDATE Books SET Quantity = Quantity - %s WHERE BookID = %s",
                        (quantity, book_id)
                    )
            
            # Commit transaction
            self.db.connection.commit()
            cursor.close()
            
            messagebox.showinfo("Success", f"Order #{order_id} placed successfully as {status}!")
            self.clear_cart()
            self.load_pending_orders()
            self.load_order_history()
            
        except Exception as e:
            self.db.connection.rollback()
            logging.error(f"Error placing order: {e}")
            messagebox.showerror("Error", f"Failed to place order: {e}")

    def load_pending_orders(self):
        """Load pending orders into the treeview"""
        for item in self.pending_orders_tree.get_children():
            self.pending_orders_tree.delete(item)
        
        orders = self.db.execute_query(
            "SELECT o.OrderID, a.CustomerName, o.OrderDate, o.TotalAmount, o.Status "
            "FROM Orders o JOIN Accounts a ON o.CustomerID = a.CustomerID "
            "WHERE o.Status = 'Pending' "
            "ORDER BY o.OrderDate DESC",
            fetch=True
        )
        
        for order in orders:
            order_id, customer, date, total, status = order
            formatted_date = date.strftime("%Y-%m-%d %H:%M")
            formatted_total = f"${total:.2f}"
            self.pending_orders_tree.insert('', 'end', values=(
                order_id, customer, formatted_date, formatted_total, status))
        
        # Clear order items tree
        for item in self.pending_items_tree.get_children():
            self.pending_items_tree.delete(item)

    def load_order_history(self):
        """Load all orders into the treeview"""
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        orders = self.db.execute_query(
            "SELECT o.OrderID, a.CustomerName, o.OrderDate, o.TotalAmount, o.Status "
            "FROM Orders o JOIN Accounts a ON o.CustomerID = a.CustomerID "
            "ORDER BY o.OrderDate DESC",
            fetch=True
        )
        
        for order in orders:
            order_id, customer, date, total, status = order
            formatted_date = date.strftime("%Y-%m-%d %H:%M")
            formatted_total = f"${total:.2f}"
            self.orders_tree.insert('', 'end', values=(
                order_id, customer, formatted_date, formatted_total, status))

    def update_order_status(self, new_status):
        """Update the status of a pending order"""
        selected = self.pending_orders_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select an order")
            return
        
        order_id = self.pending_orders_tree.item(selected[0])['values'][0]
        current_status = self.pending_orders_tree.item(selected[0])['values'][4]
        
        if current_status != "Pending":
            messagebox.showerror("Error", "Only pending orders can be modified")
            return
        
        try:
            # Start transaction
            self.db.connection.start_transaction()
            cursor = self.db.connection.cursor()
            
            if new_status == "Completed":
                # Get all order items to update book quantities
                items = self.db.execute_query(
                    "SELECT BookID, Quantity FROM OrderItems WHERE OrderID=%s",
                    (order_id,),
                    fetch=True
                )
                
                for book_id, quantity in items:
                    cursor.execute(
                        "UPDATE Books SET Quantity = Quantity - %s WHERE BookID = %s",
                        (quantity, book_id)
                    )
            
            # Update order status
            cursor.execute(
                "UPDATE Orders SET Status=%s WHERE OrderID=%s",
                (new_status, order_id)
            )
            
            # Commit transaction
            self.db.connection.commit()
            cursor.close()
            
            messagebox.showinfo("Success", f"Order #{order_id} updated to {new_status}")
            self.load_pending_orders()
            self.load_order_history()
            
        except Exception as e:
            self.db.connection.rollback()
            logging.error(f"Error updating order status: {e}")
            messagebox.showerror("Error", f"Failed to update order: {e}")

    def show_order_items(self, event):
        """Show items for the selected order"""
        selected = self.pending_orders_tree.selection()
        if not selected:
            return
        
        order_id = self.pending_orders_tree.item(selected[0])['values'][0]
        
        # Clear existing items
        for item in self.pending_items_tree.get_children():
            self.pending_items_tree.delete(item)
        
        # Load order items
        items = self.db.execute_query(
            "SELECT oi.BookID, b.BookName, oi.Quantity, oi.Price, (oi.Quantity * oi.Price) "
            "FROM OrderItems oi JOIN Books b ON oi.BookID = b.BookID "
            "WHERE oi.OrderID=%s",
            (order_id,),
            fetch=True
        )
        
        for item in items:
            book_id, book_name, quantity, price, subtotal = item
            self.pending_items_tree.insert('', 'end', values=(
                book_id, book_name, quantity, f"${price:.2f}", f"${subtotal:.2f}"))

    def show_reports(self):
        """Show reports window"""
        window = tk.Toplevel(self.root)
        window.title("Reports")
        window.geometry("900x600")

        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True)

        # Sales Report Tab
        sales_frame = ttk.Frame(notebook)
        notebook.add(sales_frame, text="Sales Report")

        # Date range selection
        date_frame = ttk.Frame(sales_frame)
        date_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(date_frame, text="From:").pack(side='left')
        self.from_date = ttk.Entry(date_frame)
        self.from_date.pack(side='left', padx=5)

        ttk.Label(date_frame, text="To:").pack(side='left', padx=(10, 0))
        self.to_date = ttk.Entry(date_frame)
        self.to_date.pack(side='left', padx=5)

        ttk.Button(
            date_frame,
            text="Generate Report",
            command=self.generate_sales_report,
            style='Accent.TButton'
        ).pack(side='left', padx=10)

        # Sales report treeview
        columns = ("Date", "Orders", "Items Sold", "Total Sales")
        self.sales_tree = ttk.Treeview(sales_frame, columns=columns, show='headings')
        
        for col in columns:
            self.sales_tree.heading(col, text=col)
            self.sales_tree.column(col, anchor='center', width=100)
        
        scrollbar = ttk.Scrollbar(sales_frame, orient='vertical', command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=scrollbar.set)
        
        self.sales_tree.pack(side='left', fill='both', expand=True, padx=10, pady=5)
        scrollbar.pack(side='right', fill='y')

        # Inventory Report Tab
        inventory_frame = ttk.Frame(notebook)
        notebook.add(inventory_frame, text="Inventory Report")

        columns = ("ID", "Book Name", "Genre", "In Stock", "Price")
        self.inventory_tree = ttk.Treeview(inventory_frame, columns=columns, show='headings')
        
        for col in columns:
            self.inventory_tree.heading(col, text=col)
            self.inventory_tree.column(col, anchor='center', width=100)
        
        self.inventory_tree.column("Book Name", width=200)
        self.inventory_tree.column("Genre", width=150)
        
        scrollbar = ttk.Scrollbar(inventory_frame, orient='vertical', command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=scrollbar.set)
        
        self.inventory_tree.pack(side='left', fill='both', expand=True, padx=10, pady=5)
        scrollbar.pack(side='right', fill='y')

        # Load initial inventory data
        self.load_inventory_report()

    def generate_sales_report(self):
        """Generate sales report for selected date range"""
        try:
            from_date = self.from_date.get().strip()
            to_date = self.to_date.get().strip()
            
            if not from_date or not to_date:
                messagebox.showerror("Error", "Please select both start and end dates")
                return
            
            # Clear existing data
            for item in self.sales_tree.get_children():
                self.sales_tree.delete(item)
            
            # Get daily sales data
            sales_data = self.db.execute_query(
                "SELECT DATE(o.OrderDate) AS SaleDate, "
                "COUNT(DISTINCT o.OrderID) AS Orders, "
                "SUM(oi.Quantity) AS ItemsSold, "
                "SUM(TotalAmount) AS TotalSales "
                "FROM Orders o "
                "JOIN OrderItems oi ON o.OrderID = oi.OrderID "
                "WHERE DATE(OrderDate) BETWEEN %s AND %s "
                "GROUP BY DATE(OrderDate) "
                "ORDER BY SaleDate",
                (from_date, to_date),
                fetch=True
            )
            
            total_sales = Decimal("0")
            
            for row in sales_data:
                sale_date, orders, items_sold, sales = row
                formatted_date = sale_date.strftime("%Y-%m-%d")
                formatted_sales = f"${sales:.2f}"
                self.sales_tree.insert('', 'end', values=(
                    formatted_date, orders, items_sold, formatted_sales))
                total_sales += sales
            
            messagebox.showinfo("Success", f"Report generated for {from_date} to {to_date}\nTotal Sales: ${total_sales:.2f}")
        
        except Exception as e:
            logging.error(f"Error generating sales report: {e}")
            messagebox.showerror("Error", f"Failed to generate report: {e}")

    def load_inventory_report(self):
        """Load inventory report data"""
        try:
            for item in self.inventory_tree.get_children():
                self.inventory_tree.delete(item)
            
            inventory = self.db.execute_query(
                "SELECT BookID, BookName, Genre, Quantity, Price FROM Books "
                "ORDER BY Genre, BookName",
                fetch=True
            )
            
            for book in inventory:
                book_id, name, genre, quantity, price = book
                formatted_price = f"${price:.2f}"
                self.inventory_tree.insert('', 'end', values=(
                    book_id, name, genre, quantity, formatted_price))
        
        except Exception as e:
            logging.error(f"Error loading inventory report: {e}")
            messagebox.showerror("Error", f"Failed to load inventory: {e}")

    def show_settings(self):
        """Show settings window"""
        messagebox.showinfo("Settings", "Settings functionality will be implemented in a future version")

    def on_closing(self):
        """Handle application closing"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.db.close()
            self.root.destroy()

def main():
    """Main function to run the application"""
    try:
        root = tk.Tk()
        app = BookstoreApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        logging.critical(f"Application error: {e}")
        messagebox.showerror("Critical Error", f"The application encountered an error: {e}")

if __name__ == "__main__":
    main()
