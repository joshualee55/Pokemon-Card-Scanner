"""Owner tools.   python -m app.admin list
                 python -m app.admin reset <username>      (sets a new password, logs that user out)
                 python -m app.admin delete <username>     (removes the user AND their collection)"""
import sys, getpass
from .db import conn
from .auth import hash_pw, check_new

def main(a):
    db = conn()
    if not a or a[0] == "list":
        for r in db.execute("SELECT u.username, (SELECT COUNT(*) FROM collection c WHERE c.user_id=u.id) n FROM users u"):
            print(f"{r['username']}: {r['n']} cards")
    elif a[0] == "reset" and len(a) == 2:
        u = db.execute("SELECT id FROM users WHERE username=?", (a[1],)).fetchone()
        if not u: sys.exit("No such user. Run: python -m app.admin list")
        pw = getpass.getpass("New password (typing is hidden): ")
        if (e := check_new(a[1], pw)): sys.exit(e)
        db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(pw), u["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],)); db.commit()
        print("Password changed for", a[1])
    elif a[0] == "delete" and len(a) == 2:
        u = db.execute("SELECT id FROM users WHERE username=?", (a[1],)).fetchone()
        if not u: sys.exit("No such user.")
        if input(f"Delete {a[1]} and all their cards? Type yes: ") != "yes": sys.exit("Cancelled")
        for t in ("collection", "sessions"): db.execute(f"DELETE FROM {t} WHERE user_id=?", (u["id"],))
        db.execute("DELETE FROM users WHERE id=?", (u["id"],)); db.commit(); print("Deleted", a[1])
    else: print(__doc__)

if __name__ == "__main__": main(sys.argv[1:])
