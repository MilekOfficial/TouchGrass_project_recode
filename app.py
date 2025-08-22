from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient, ASCENDING
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = "supersecret"

# Connect to MongoDB (replace with your own connection string if needed)
client = MongoClient(
    "mongodb+srv://server:m0XXrqUMUsqemcLv@cluster0.mi2bcfi.mongodb.net/touchgrass?retryWrites=true&w=majority&appName=Cluster0"
)
db = client["touchgrass"]
users_col = db["users"]
posts_col = db["posts"]
follows_col = db["follows"]
notifications_col = db["notifications"]

# Ensure useful indexes (idempotent)
try:
    users_col.create_index([("username", ASCENDING)], unique=True)
    follows_col.create_index([("follower_id", ASCENDING), ("followee_id", ASCENDING)], unique=True)
    posts_col.create_index([("created_at", ASCENDING)])
except Exception:
    # Index creation failures shouldn't crash the app in dev
    pass

DEFAULT_BADGES = {
    'early_adopter': False,
    'verified': False,
    'premium': False,
    'moderator': False,
    'admin': False
}

def time_ago(dt):
    from datetime import datetime, timezone

    # If dt has no tzinfo, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds//60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds//3600)}h ago"
    else:
        return f"{int(seconds//86400)}d ago"


app.jinja_env.globals.update(time_ago=time_ago)

ALLOWED_EMOJIS = {"❤️","🔥","😂","👍","🌱"}

def _current_user_id():
    if "user_id" not in session:
        return None
    try:
        return ObjectId(session["user_id"])
    except Exception:
        return None

def _is_following(follower_id: ObjectId, followee_id: ObjectId) -> bool:
    if not follower_id or not followee_id:
        return False
    return follows_col.find_one({"follower_id": follower_id, "followee_id": followee_id}) is not None

@app.context_processor
def inject_unread_notifications():
    """Provide unread notifications count to all templates as unread_notifications_count."""
    try:
        current_oid = _current_user_id()
        if current_oid:
            count = notifications_col.count_documents({"to_user_id": current_oid, "read": False})
        else:
            count = 0
    except Exception:
        count = 0
    return {"unread_notifications_count": count}

@app.context_processor
def inject_globals():
    def get_user_preferences(username):
        if not username:
            return {'dark_mode': False}
        user = users_col.find_one(
            {"username": username},
            {"dark_mode": 1, "badges": 1, "_id": 0}
        )
        return user or {'dark_mode': False}
    
    # Get notification count if user is logged in
    notification_count = 0
    if 'user_id' in session:
        notification_count = notifications_col.count_documents({
            'to_user_id': ObjectId(session['user_id']),
            'read': False
        })
    
    return {
        'get_user_preferences': get_user_preferences,
        'current_user': session.get('username'),
        'notification_count': {'unread_notifications_count': notification_count},
        'users_col': users_col,
        'posts_col': posts_col,
        'follows_col': follows_col,
        'notifications_col': notifications_col
    }

@app.route("/")
def index():
    posts = list(posts_col.find().sort("created_at", -1))
    for post in posts:
        post["reactions"] = post.get("reactions", {})
        for emoji in ["❤️","🔥","😂","👍","🌱"]:
            post["reactions"].setdefault(emoji, 0)
        post["comments"] = post.get("comments", [])
    return render_template("index.html", posts=posts)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        
        if users_col.find_one({"username": username}):
            flash("Username already taken")
            return redirect(url_for("register"))
            
        user = {
            "username": username,
            "password": password,
            "created_at": datetime.now(timezone.utc),
            "dark_mode": False,
            "badges": DEFAULT_BADGES.copy(),
            "bio": "",
            "avatar_url": ""
        }
        users_col.insert_one(user)
        session["user_id"] = str(user["_id"])
        session["username"] = username
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            return redirect(url_for("index"))
        flash("Invalid login")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/post", methods=["POST"])
def post():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    content = request.form["content"]
    
    # Extract hashtags
    hashtags = list(set(part[1:] for part in content.split() if part.startswith('#')))
    
    post_data = {
        "author": session["username"],
        "content": content,
        "hashtags": hashtags,
        "created_at": datetime.now(timezone.utc),
        "reactions": {},
        "comments": []
    }
    
    posts_col.insert_one(post_data)
    return redirect(url_for("index"))

@app.route("/react/<post_id>/<emoji>", methods=["POST"])
def react(post_id, emoji):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if emoji not in ALLOWED_EMOJIS:
        flash("Unsupported reaction")
        return redirect(url_for("index"))
    try:
        oid = ObjectId(post_id)
    except Exception:
        flash("Invalid post id")
        return redirect(url_for("index"))
    post = posts_col.find_one({"_id": oid})
    if not post:
        return redirect(url_for("index"))
    reactions = post.get("reactions", {})
    reactions[emoji] = reactions.get(emoji, 0) + 1
    posts_col.update_one({"_id": oid}, {"$set": {"reactions": reactions}})
    return redirect(url_for("index"))

@app.route("/comment/<post_id>", methods=["POST"])
def comment(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    text = request.form["comment"]
    try:
        oid = ObjectId(post_id)
    except Exception:
        flash("Invalid post id")
        return redirect(url_for("index"))
    posts_col.update_one({"_id": oid}, {"$push": {"comments": {
        "username": session["username"],
        "text": text
    }}})
    return redirect(url_for("index"))

@app.route("/user/<username>")
def user_profile(username):
    user = users_col.find_one({"username": username})
    if not user:
        flash("User not found")
        return redirect(url_for("index"))
    posts = list(posts_col.find({"author": username}).sort("created_at", -1))
    # Compute follow stats
    followers_count = follows_col.count_documents({"followee_id": user["_id"]})
    following_count = follows_col.count_documents({"follower_id": user["_id"]})
    current_oid = _current_user_id()
    is_following = _is_following(current_oid, user["_id"]) if current_oid else False
    return render_template(
        "profile.html",
        user=user,
        posts=posts,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
    )

@app.route("/follow/<username>", methods=["POST"])
def follow_user(username):
    if "user_id" not in session:
        return redirect(url_for("login"))
    target = users_col.find_one({"username": username})
    if not target:
        flash("User not found")
        return redirect(url_for("index"))
    follower_oid = _current_user_id()
    if not follower_oid:
        return redirect(url_for("login"))
    if str(target["_id"]) == session.get("user_id"):
        flash("You cannot follow yourself")
        return redirect(url_for("user_profile", username=username))
    try:
        follows_col.insert_one({
            "follower_id": follower_oid,
            "followee_id": target["_id"],
            "created_at": datetime.now(timezone.utc)
        })
        # Create notification for the target user
        notifications_col.insert_one({
            "to_user_id": target["_id"],
            "type": "follow",
            "created_at": datetime.now(timezone.utc),
            "data": {"from_username": session.get("username")},
            "read": False,
        })
    except Exception:
        # Likely already following due to unique index
        pass
    return redirect(url_for("user_profile", username=username))

@app.route("/unfollow/<username>", methods=["POST"])
def unfollow_user(username):
    if "user_id" not in session:
        return redirect(url_for("login"))
    target = users_col.find_one({"username": username})
    if not target:
        return redirect(url_for("index"))
    follower_oid = _current_user_id()
    if not follower_oid:
        return redirect(url_for("login"))
    follows_col.delete_one({"follower_id": follower_oid, "followee_id": target["_id"]})
    return redirect(url_for("user_profile", username=username))

@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))
    current_oid = _current_user_id()
    notes = list(notifications_col.find({"to_user_id": current_oid}).sort("created_at", -1))
    return render_template("notifications.html", notifications=notes)

@app.route("/notifications/read_all", methods=["POST"])
def notifications_read_all():
    if "user_id" not in session:
        return redirect(url_for("login"))
    current_oid = _current_user_id()
    notifications_col.update_many({"to_user_id": current_oid, "read": False}, {"$set": {"read": True}})
    return redirect(url_for("notifications"))

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("login"))
    current_oid = _current_user_id()
    user = users_col.find_one({"_id": current_oid})
    if request.method == "POST":
        avatar_url = request.form.get("avatar_url", "").strip()
        bio = request.form.get("bio", "").strip()
        users_col.update_one({"_id": current_oid}, {"$set": {"avatar_url": avatar_url, "bio": bio}})
        flash("Settings updated")
        return redirect(url_for("settings"))
    return render_template("settings.html", user=user)

@app.route("/post/delete/<post_id>", methods=["POST"])
def delete_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    try:
        oid = ObjectId(post_id)
        post = posts_col.find_one({"_id": oid})
        
        # Check if the current user is the author of the post
        if not post or post["author"] != session["username"]:
            flash("You can only delete your own posts")
            return redirect(url_for("index"))
            
        posts_col.delete_one({"_id": oid})
        flash("Post deleted successfully")
    except Exception as e:
        flash("Error deleting post")
        
    return redirect(url_for("index"))

@app.route("/post/edit/<post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        oid = ObjectId(post_id)
        post = posts_col.find_one({"_id": oid})
        
        # Check if the current user is the author of the post
        if not post or post["author"] != session["username"]:
            flash("You can only edit your own posts")
            return redirect(url_for("index"))
            
        if request.method == "POST":
            new_content = request.form["content"]
            posts_col.update_one(
                {"_id": oid},
                {"$set": {"content": new_content, "edited_at": datetime.now(timezone.utc)}}
            )
            flash("Post updated successfully")
            return redirect(url_for("index"))
            
        return render_template("edit_post.html", post=post)
        
    except Exception as e:
        flash("Error editing post")
        return redirect(url_for("index"))

@app.route("/comment/delete/<post_id>/<int:comment_index>", methods=["POST"])
def delete_comment(post_id, comment_index):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        oid = ObjectId(post_id)
        post = posts_col.find_one({"_id": oid})
        
        if not post or comment_index >= len(post.get("comments", [])):
            flash("Comment not found")
            return redirect(url_for("index"))
            
        comment = post["comments"][comment_index]
        
        # Check if the current user is the author of the comment or the post
        if comment["username"] != session["username"] and post["author"] != session["username"]:
            flash("You can only delete your own comments")
            return redirect(url_for("index"))
            
        # Remove the comment by index
        posts_col.update_one(
            {"_id": oid},
            {"$unset": {f"comments.{comment_index}": ""}}
        )
        
        # Clean up the null values in the array
        posts_col.update_one(
            {"_id": oid},
            [{"$set": {"comments": {"$ifNull": [{"$filter": {"input": "$comments", "cond": {"$ne": ["$$this", None]}}}, []]}}}]
        )
        
        flash("Comment deleted successfully")
        
    except Exception as e:
        flash("Error deleting comment")
        
    return redirect(url_for("index"))

@app.route("/comment/edit/<post_id>/<int:comment_index>", methods=["GET", "POST"])
def edit_comment(post_id, comment_index):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        oid = ObjectId(post_id)
        post = posts_col.find_one({"_id": oid})
        
        if not post or comment_index >= len(post.get("comments", [])):
            flash("Comment not found")
            return redirect(url_for("index"))
            
        comment = post["comments"][comment_index]
        
        # Check if the current user is the author of the comment
        if comment["username"] != session["username"]:
            flash("You can only edit your own comments")
            return redirect(url_for("index"))
            
        if request.method == "POST":
            new_text = request.form["comment"]
            
            # Update the specific comment
            posts_col.update_one(
                {"_id": oid},
                {"$set": {f"comments.{comment_index}.text": new_text, f"comments.{comment_index}.edited": True}}
            )
            
            flash("Comment updated successfully")
            return redirect(url_for("index"))
            
        return render_template("edit_comment.html", 
                             post_id=post_id, 
                             comment_index=comment_index,
                             comment=comment)
        
    except Exception as e:
        flash("Error editing comment")
        return redirect(url_for("index"))

@app.route("/search")
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))
        
    # Search in posts
    post_results = list(posts_col.find({
        "$or": [
            {"content": {"$regex": query, "$options": "i"}},
            {"author": {"$regex": query, "$options": "i"}}
        ]
    }).sort("created_at", -1))
    
    # Search for users
    user_results = list(users_col.find({
        "username": {"$regex": query, "$options": "i"}
    }, {"password": 0}))  # Don't return passwords
    
    return render_template(
        "search.html",
        query=query,
        posts=post_results,
        users=user_results
    )

@app.route("/toggle_dark_mode", methods=["POST"])
def toggle_dark_mode():
    if "user_id" not in session:
        return "Unauthorized", 401
    
    current_oid = _current_user_id()
    user = users_col.find_one({"_id": current_oid})
    new_mode = not user.get("dark_mode", False)
    
    users_col.update_one(
        {"_id": current_oid},
        {"$set": {"dark_mode": new_mode}}
    )
    
    return "", 204

@app.route("/hashtag/<hashtag>")
def view_hashtag(hashtag):
    posts = list(posts_col.find({"hashtags": hashtag.lower()}).sort("created_at", -1))
    return render_template("hashtag.html", hashtag=hashtag, posts=posts)

if __name__ == "__main__":
    app.run(debug=True)
