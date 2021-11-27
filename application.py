import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Acquire user's cash and stock holdings
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    portfolio = db.execute("SELECT * FROM transactions WHERE user_id = :id", id=session["user_id"])
    total = 0
    # Update price of each share
    for share in portfolio:
        company = lookup(share["stock"])
        price = company["price"]
        share["price"] = price
        total += price*share["shares"]
    return render_template("index.html", portfolio=portfolio, cash=cash, total=total)
    

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    
    # Load purchasing link
    if request.method == "GET":
        return render_template("buy.html")
    else:
        # Ensures proper symbol and shares entered
        if not request.form.get("symbol"):
            return apology("Please enter a symbol")
        elif request.form.get("symbol") == None:
            return apology("Invalid symbol")
        elif int(request.form.get("shares")) < 1:
            return apology("Invalid number of shares")
        
        # Acquire stock price and user's current cash
        stock = lookup(request.form.get("symbol"))
        curr_price = float(stock["price"])
        shares = int(request.form.get("shares"))
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        
        # Determine if user has enough cash
        if curr_price > cash[0]["cash"] * int(request.form.get("shares")):
            return apology("Not enough cash to purchase")
        
        # Creates a new table of transactions
        db.execute("INSERT INTO transactions (user_id, stock, shares, price) VALUES (?,?,?,?)", 
                   session["user_id"], request.form.get("symbol"), shares, curr_price)
        # Updates user table cash values after transaction
        db.execute("UPDATE users SET cash = :update WHERE id = :id", update=cash[0]["cash"]-curr_price*shares, id=session["user_id"])
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :id", id=session["user_id"])
    return render_template("history.html", transactions=transactions)
        

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # Load quote page
    if request.method == "GET":
        return render_template("quote.html")
    else:
        # No symbol found
        if not request.form.get("symbol"):
            return apology("Please enter a valid symbol")
        elif request.form.get("symbol") == None:
            return apology("Invalid symbol")
        else:
            price = lookup(request.form.get("symbol"))
            return render_template("quoted.html", price=price, symbol=request.form.get("symbol"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    
    # Open registration page
    if request.method == "GET":
        return render_template("register.html")
        
    else:
        # No username error
        if not request.form.get("username"):
            return apology("Username required")
        
        # No password error
        elif not request.form.get("password"):
            return apology("Password required")
            
        # No confirmation password error
        elif not request.form.get("confirmation"):
            return apology("Please confirm your password")
            
        # Username taken error
        elif len(db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))) == 1:
            return apology("Username taken; please try another")
            
        # Incorrect confirmation password
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Please ensure the passwords match")
            
        username = request.form.get("username")
        password = request.form.get("password")
        password_hash = generate_password_hash(request.form.get("password"))
        
        # Input username and password into database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password_hash)", 
                   username=username, password_hash=password_hash)
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Loads selling page
    if request.method == "GET":
        return render_template("sell.html")
    else:
        # Checks for errors in sale
        if not request.form.get("symbol"):
            return apology("Please enter a symbol")
        elif request.form.get("symbol") == None:
            return apology("Invalid symbol")
        elif request.form.get("shares") < 1:
            return apology("Please enter a valid number of shares")
            
        # Ensures user owns adequate number of shares for sale
        current_shares = db.execute("SELECT shares FROM transactions WHERE user_id = :id AND stock = :stock", 
                                    id=session["user_id"], stock=request.form.get("symbol"))    
        shares = int(request.form.get("shares"))
        if current_shares[0]["shares"] == None:
            return apology("You do not own any shares of this stock")
        elif current_shares[0]["shares"] < shares:
            return apology("You do not own enough shares of this stock")
        stock = lookup(request.form.get("symbol"))
        curr_price = float(stock["price"])
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        # Takes out sold stocks from transaction table
        db.execute("INSERT INTO transactions (user_id, stock, shares, price) VALUES (?,?,?,?)", 
                   session["user_id"], request.form.get("symbol"), -shares, curr_price)
        # Updates user table cash values after transaction
        db.execute("UPDATE users SET cash = :update WHERE id = :id", update=cash+curr_price*shares, id=session["user_id"])
        return redirect("/")
    

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
