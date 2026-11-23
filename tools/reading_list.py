"""
tools/reading_list.py - AI Tool definitions and handlers for the Reading List domain.
"""

from datetime import datetime
import os
from google.genai import types


ADD_BOOK_TOOL = types.FunctionDeclaration(
    name="add_book",
    description="Adds a book to the user's reading list on PocketBase.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(
                type=types.Type.STRING,
                description="The title of the book",
            ),
            "author": types.Schema(
                type=types.Type.STRING,
                description="The author of the book (optional)",
            ),
            "status": types.Schema(
                type=types.Type.STRING,
                description="Reading status of the book",
                enum=["planned", "reading", "read", "dropped"],
            ),
            "publish_date": types.Schema(
                type=types.Type.STRING,
                description="The publication date or year (optional)",
            ),
            "isbn": types.Schema(
                type=types.Type.STRING,
                description="ISBN of the book (optional)",
            ),
            "start_date": types.Schema(
                type=types.Type.STRING,
                description="Start reading date (YYYY-MM-DD) (optional)",
            ),
            "end_date": types.Schema(
                type=types.Type.STRING,
                description="Finished reading date (YYYY-MM-DD) (optional)",
            ),
            "completed": types.Schema(
                type=types.Type.STRING,
                description="Completion details or notes (optional)",
            ),
            "description": types.Schema(
                type=types.Type.STRING,
                description="Synopsis, summary, or review notes (optional)",
            ),
            "current_page": types.Schema(
                type=types.Type.INTEGER,
                description="Current page number the user is on (>= 0).",
            ),
            "total_pages": types.Schema(
                type=types.Type.INTEGER,
                description="Total number of pages in the book (>= 0). Auto-filled from book metadata if omitted when adding.",
            ),
            "rating": types.Schema(
                type=types.Type.INTEGER,
                description="User rating for the book from 1 to 5 stars (0 to clear).",
            ),
        },
        required=["title"],
    ),
)

GET_READING_LIST_TOOL = types.FunctionDeclaration(
    name="get_reading_list",
    description="Retrieves the user's reading list from PocketBase, including book titles, authors, statuses, page progress, ratings, dates, completion info, and descriptions. Call this ONLY when the user explicitly asks about their reading list or asks for book recommendations.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "status": types.Schema(
                type=types.Type.STRING,
                description="Optional filter by status: 'planned', 'reading', 'read', 'dropped', or 'all'",
            ),
        },
    ),
)

UPDATE_BOOK_TOOL = types.FunctionDeclaration(
    name="update_book",
    description="Updates an existing book on the user's reading list on PocketBase by title, author, ISBN, or ID (e.g. status, page progress, total pages, rating, reading dates, completion progress, description, ISBN).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The title, author, ISBN, or ID of the book to update",
            ),
            "title": types.Schema(
                type=types.Type.STRING,
                description="New title for the book (optional)",
            ),
            "author": types.Schema(
                type=types.Type.STRING,
                description="New author for the book (optional)",
            ),
            "status": types.Schema(
                type=types.Type.STRING,
                description="New reading status",
                enum=["planned", "reading", "read", "dropped"],
            ),
            "start_date": types.Schema(
                type=types.Type.STRING,
                description="Date started reading (YYYY-MM-DD) (optional)",
            ),
            "end_date": types.Schema(
                type=types.Type.STRING,
                description="Date finished reading (YYYY-MM-DD) (optional)",
            ),
            "completed": types.Schema(
                type=types.Type.STRING,
                description="Completion details or notes (optional)",
            ),
            "publish_date": types.Schema(
                type=types.Type.STRING,
                description="Publication date or year (optional)",
            ),
            "description": types.Schema(
                type=types.Type.STRING,
                description="Synopsis, summary, or review notes (optional)",
            ),
            "isbn": types.Schema(
                type=types.Type.STRING,
                description="ISBN of the book (optional)",
            ),
            "current_page": types.Schema(
                type=types.Type.INTEGER,
                description="Current page number the user is on (>= 0).",
            ),
            "total_pages": types.Schema(
                type=types.Type.INTEGER,
                description="Total number of pages in the book (>= 0).",
            ),
            "rating": types.Schema(
                type=types.Type.INTEGER,
                description="User rating for the book from 1 to 5 stars (0 to clear).",
            ),
        },
        required=["query"],
    ),
)

DELETE_BOOK_TOOL = types.FunctionDeclaration(
    name="delete_book",
    description="Removes a book from the user's reading list on PocketBase by title, author, ISBN, or ID.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The title, author, ISBN, or ID of the book to remove",
            ),
        },
        required=["query"],
    ),
)


async def handle_add_book(bot, args: dict, user_id: str = None, context: dict | None = None, **kwargs) -> str:
    """Handler for the add_book AI tool."""
    if isinstance(args, str) and isinstance(user_id, dict):
        args, user_id = user_id, args
    elif user_id is None and "user_id" in kwargs:
        user_id = kwargs["user_id"]

    reading_list_cog = bot.get_cog("ReadingList")
    if not reading_list_cog:
        return "Error: ReadingList cog is unavailable."

    title = str(args.get("title", "")).strip() if args else ""
    author = str(args.get("author", "")).strip() if args else ""
    status = str(args.get("status", "planned")).strip().lower() if args else "planned"
    publish_date = str(args.get("publish_date", args.get("publishDate", ""))).strip() if args else ""
    isbn = str(args.get("isbn", "")).strip() if args else ""
    start_date = str(args.get("start_date", args.get("startDate", ""))).strip() if args else ""
    end_date = str(args.get("end_date", args.get("endDate", ""))).strip() if args else ""
    completed = str(args.get("completed", "")).strip() if args else ""
    description = str(args.get("description", "")).strip() if args else ""
    raw_curr = args.get("current_page", args.get("currentPage")) if args else None
    raw_total = args.get("total_pages", args.get("totalPages")) if args else None
    raw_rating = args.get("rating") if args else None

    if not title and not isbn:
        return "Error: Title or ISBN is required."

    api_key = getattr(reading_list_cog, "google_books_api_key", None) or os.getenv("GOOGLE_BOOKS_API_KEY")
    image_url = ""
    cover_filename = None
    cover_data = None
    fetched_total_pages = 0

    # Automatically fetch book data (Google Books with Open Library fallback)
    from utils import google_books

    search_query = (
        isbn
        if isbn
        else (
            f"{title} {author}".strip()
            if (title and author)
            else (title or "")
        )
    )
    if search_query:
        book_data = await google_books.fetch_book_data(search_query, api_key)
        if isinstance(book_data, dict):
            title = title or book_data.get("title", "")
            authors = book_data.get("authors", [])
            if not author and authors and authors != ["Unknown Author"]:
                author = ", ".join(authors)
            if (
                not publish_date
                and book_data.get("publishedDate")
                and book_data.get("publishedDate") != "Unknown"
            ):
                publish_date = book_data.get("publishedDate")
            if not isbn and book_data.get("isbn"):
                isbn = book_data.get("isbn")
            image_url = book_data.get("thumbnail", "")
            fetched_total_pages = int(book_data.get("pageCount") or 0)
            desc = book_data.get("description", "")
            if not description and desc and desc != "No description available.":
                description = desc

            if image_url:
                cover_filename, cover_data = await google_books.download_image(
                    image_url
                )

    final_total_pages = max(0, int(raw_total if raw_total is not None else fetched_total_pages))
    final_current_page = max(0, int(raw_curr if raw_curr is not None else 0))
    if status == "read" and final_total_pages > 0 and final_current_page == 0:
        final_current_page = final_total_pages
    final_rating = max(0, min(5, int(raw_rating if raw_rating is not None else 0)))

    today = datetime.now().strftime("%Y-%m-%d")
    final_start = start_date if start_date else (today if status in ["read", "reading"] else "")
    final_end = end_date if end_date else (today if status == "read" else "")

    await reading_list_cog.add_book_to_pocketbase(
        discord_id=user_id,
        title=title or "Unknown Title",
        author=author or "Unknown Author",
        status_val=(
            status
            if status in ["planned", "reading", "read", "dropped"]
            else "planned"
        ),
        publish_date=publish_date if publish_date != "Unknown" else "",
        isbn=isbn,
        final_start_date=final_start,
        final_end_date=final_end,
        image_url=image_url,
        description=description,
        cover_filename=cover_filename,
        cover_data=cover_data,
        completed=completed,
        current_page=final_current_page,
        total_pages=final_total_pages,
        rating=final_rating,
    )
    details = []
    if final_total_pages > 0 or final_current_page > 0:
        if final_total_pages > 0:
            pct = round((final_current_page / final_total_pages) * 100)
            details.append(f"progress: {final_current_page}/{final_total_pages} pages ({pct}%)")
        else:
            details.append(f"page: {final_current_page}")
    if final_rating > 0:
        details.append(f"rating: {final_rating}/5")
    detail_str = f", {', '.join(details)}" if details else ""
    return f"Successfully added '{title or 'Unknown Title'}' by {author or 'Unknown Author'} (status: {status}{detail_str}) to the reading list."


async def handle_get_reading_list(bot, args: dict, user_id: str = None, context: dict | None = None, **kwargs) -> str:
    """Handler for the get_reading_list AI tool."""
    if isinstance(args, str) and isinstance(user_id, dict):
        args, user_id = user_id, args
    elif user_id is None and "user_id" in kwargs:
        user_id = kwargs["user_id"]

    reading_list_cog = bot.get_cog("ReadingList")
    if not reading_list_cog:
        return "Error: ReadingList cog is unavailable."
    status_filter = str(args.get("status", "")).strip().lower() if args else ""
    all_books = await reading_list_cog.fetch_reading_list(user_id)
    if not all_books:
        return "No books found in reading list."

    # Compute reading stats summary across the library
    reading_count = sum(1 for b in all_books if b.get("status", "").lower() == "reading")
    read_count = sum(1 for b in all_books if b.get("status", "").lower() == "read")
    total_pages_read = sum(
        (b.get("totalPages") or 0)
        if b.get("status", "").lower() == "read" and (b.get("totalPages") or 0) > 0
        else (b.get("currentPage") or 0)
        for b in all_books
    )
    stats_header = f"Stats: {reading_count} reading, {read_count} read, {total_pages_read} total pages read"

    books = all_books
    if status_filter and status_filter != "all":
        filtered_books = [
            b for b in all_books if b.get("status", "").lower() == status_filter
        ]
        if filtered_books:
            books = filtered_books
        else:
            return f"No books found with status '{status_filter}' in reading list."

    formatted = [stats_header]
    for b in books:
        title = b.get("title", "Unknown")
        author = b.get("author", "Unknown")
        status = b.get("status", "unknown")
        line = f"- **{title}** by {author} (Status: {status})"
        extras = []
        curr_p = int(b.get("currentPage") or 0)
        total_p = int(b.get("totalPages") or 0)
        rating = int(b.get("rating") or 0)
        if total_p > 0:
            pct = round((curr_p / total_p) * 100)
            extras.append(f"Progress: {curr_p}/{total_p} pages ({pct}%)")
        elif curr_p > 0:
            extras.append(f"Page: {curr_p}")
        if rating > 0:
            extras.append(f"Rating: {rating}/5 ★")
        if b.get("isbn"):
            extras.append(f"ISBN: {b['isbn']}")
        if b.get("publishDate"):
            extras.append(f"Published: {b['publishDate']}")
        if b.get("startDate"):
            extras.append(f"Started: {b['startDate']}")
        if b.get("endDate"):
            extras.append(f"Finished: {b['endDate']}")
        if b.get("completed"):
            extras.append(f"Completed: {b['completed']}")
        if b.get("description"):
            desc = b["description"]
            desc_snippet = desc[:120] + "..." if len(desc) > 120 else desc
            extras.append(f"Description: {desc_snippet}")
        if extras:
            line += f" [{', '.join(extras)}]"
        formatted.append(line)

    return "\n".join(formatted)


async def handle_update_book(bot, args: dict, user_id: str = None, context: dict | None = None, **kwargs) -> str:
    """Handler for the update_book AI tool."""
    if isinstance(args, str) and isinstance(user_id, dict):
        args, user_id = user_id, args
    elif user_id is None and "user_id" in kwargs:
        user_id = kwargs["user_id"]

    reading_list_cog = bot.get_cog("ReadingList")
    if not reading_list_cog:
        return "Error: ReadingList cog is unavailable."

    query = str(args.get("query", args.get("book", args.get("title", "")))).strip() if args else ""
    if not query:
        return "Error: Book query (title, author, ISBN, or ID) is required."

    update_data = {}
    if "title" in args and args["title"] is not None:
        update_data["title"] = args["title"]
    if "author" in args and args["author"] is not None:
        update_data["author"] = args["author"]
    if "status" in args and args["status"] is not None:
        update_data["status"] = args["status"]
    if "start_date" in args and args["start_date"] is not None:
        update_data["startDate"] = args["start_date"]
    elif "startDate" in args and args["startDate"] is not None:
        update_data["startDate"] = args["startDate"]
    if "end_date" in args and args["end_date"] is not None:
        update_data["endDate"] = args["end_date"]
    elif "endDate" in args and args["endDate"] is not None:
        update_data["endDate"] = args["endDate"]
    if "completed" in args and args["completed"] is not None:
        update_data["completed"] = args["completed"]
    if "publish_date" in args and args["publish_date"] is not None:
        update_data["publishDate"] = args["publish_date"]
    elif "publishDate" in args and args["publishDate"] is not None:
        update_data["publishDate"] = args["publishDate"]
    if "description" in args and args["description"] is not None:
        update_data["description"] = args["description"]
    if "isbn" in args and args["isbn"] is not None:
        update_data["isbn"] = args["isbn"]
    if "current_page" in args and args["current_page"] is not None:
        update_data["currentPage"] = args["current_page"]
    elif "currentPage" in args and args["currentPage"] is not None:
        update_data["currentPage"] = args["currentPage"]
    if "total_pages" in args and args["total_pages"] is not None:
        update_data["totalPages"] = args["total_pages"]
    elif "totalPages" in args and args["totalPages"] is not None:
        update_data["totalPages"] = args["totalPages"]
    if "rating" in args and args["rating"] is not None:
        update_data["rating"] = args["rating"]

    if not update_data:
        return "Error: No update parameters provided."

    try:
        updated_rec = await reading_list_cog.update_book_in_pocketbase(
            user_id=user_id,
            book_query=query,
            update_data=update_data,
        )
        title = updated_rec.get("title", query)
        status = updated_rec.get("status", "unknown")
        details = [f"Status: {status}"]
        curr_p = int(updated_rec.get("currentPage") or 0)
        total_p = int(updated_rec.get("totalPages") or 0)
        rating = int(updated_rec.get("rating") or 0)
        if total_p > 0:
            pct = round((curr_p / total_p) * 100)
            details.append(f"Progress: {curr_p}/{total_p} pages ({pct}%)")
        elif curr_p > 0:
            details.append(f"Page: {curr_p}")
        if rating > 0:
            details.append(f"Rating: {rating}/5")
        return f"Successfully updated '{title}' ({', '.join(details)})."
    except Exception as e:
        return f"Error updating book: {e}"


async def handle_delete_book(bot, args: dict, user_id: str = None, context: dict | None = None, **kwargs) -> str:
    """Handler for the delete_book AI tool."""
    if isinstance(args, str) and isinstance(user_id, dict):
        args, user_id = user_id, args
    elif user_id is None and "user_id" in kwargs:
        user_id = kwargs["user_id"]

    reading_list_cog = bot.get_cog("ReadingList")
    if not reading_list_cog:
        return "Error: ReadingList cog is unavailable."
    query = str(args.get("query", args.get("title", ""))).strip() if args else ""
    if not query:
        return "Error: Book title, ISBN, or ID is required."
    res = await reading_list_cog.delete_book_from_pocketbase(user_id, query)
    return res
