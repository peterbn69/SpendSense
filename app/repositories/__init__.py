# The only code that queries the database. Functions never commit.
# Everything that reads or changes expenses takes user_id, so another user's expense is not found.
