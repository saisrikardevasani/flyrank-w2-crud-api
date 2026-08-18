# Task API (FlyRank W2 / A1)

A small to-do API built with FastAPI: create, read, update and delete tasks. Tasks live in a
Python list inside the running process, so there is no database and a restart puts the list
back to the three examples it starts with. That is the point of the exercise, and
[the mortality experiment](#the-mortality-experiment) below shows what it costs.

FastAPI generates Swagger UI from the code, so the interactive docs sit at
http://localhost:8000/docs with nothing extra installed.

## Run it

You need Python 3.10 or newer (`python3 --version` tells you). From a clean checkout:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn main:app --reload
```

Open http://localhost:8000/docs and hit **Try it out** on any endpoint.

If your `python3` is older, point the first step at a newer one (`python3.11 -m venv .venv`)
and leave the rest of the command alone.

To run the checks: `.venv/bin/python test_api.py`, which prints `all checks passed`.

## Endpoints

| Method | Path | Does | Success | Errors |
|---|---|---|---|---|
| GET | `/` | What this API is | 200 | |
| GET | `/health` | Liveness check, returns `{"status":"ok"}` | 200 | |
| GET | `/tasks` | List tasks. Optional `?done=`, `?search=`, `?limit=`, `?offset=` | 200 | 400 bad query |
| GET | `/tasks/{id}` | One task | 200 | 404 unknown id |
| POST | `/tasks` | Create from `{"title": "Buy milk"}` | 201 | 400 missing or empty title |
| PUT | `/tasks/{id}` | Replace `title`, optionally `done` | 200 | 400 invalid body, 404 unknown id |
| DELETE | `/tasks/{id}` | Remove it, empty body | 204 | 404 unknown id |
| GET | `/stats` | `{"total":3,"done":1,"open":2}` | 200 | |
| POST | `/reset` | Restore the three example tasks | 200 | |

A task looks like `{"id": 1, "title": "Read the assignment", "done": true}`. Every error comes
back in the same shape, `{"error": "..."}`, whatever went wrong.

## Proof: the full CRUD cycle in curl

```console
$ curl -i http://localhost:8000/tasks
HTTP/1.1 200 OK
content-type: application/json

[{"id":1,"title":"Read the assignment","done":true},{"id":2,"title":"Build the CRUD API","done":false},{"id":3,"title":"Push it to GitHub","done":false}]

$ curl -i -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d '{"title":"Buy milk"}'
HTTP/1.1 201 Created
content-type: application/json

{"id":4,"title":"Buy milk","done":false}

$ curl -i -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d '{}'
HTTP/1.1 400 Bad Request
content-type: application/json

{"error":"title: Field required"}

$ curl -i http://localhost:8000/tasks/4
HTTP/1.1 200 OK
content-type: application/json

{"id":4,"title":"Buy milk","done":false}

$ curl -i -X PUT http://localhost:8000/tasks/4 -H "Content-Type: application/json" -d '{"title":"Buy oat milk","done":true}'
HTTP/1.1 200 OK
content-type: application/json

{"id":4,"title":"Buy oat milk","done":true}

$ curl -i -X DELETE http://localhost:8000/tasks/4
HTTP/1.1 204 No Content

$ curl -i http://localhost:8000/tasks/99
HTTP/1.1 404 Not Found
content-type: application/json

{"error":"Task 99 not found"}
```

The `date` and `server` headers are trimmed out of every response above to keep it readable.

## Swagger UI

Every endpoint is listed, and **Try it out** sends the real request:

![Swagger UI at /docs](docs/swagger-ui.png)

## Extras

- **Filtering**: `GET /tasks?done=true` returns only the finished ones.
- **Search**: `GET /tasks?search=github` matches on the title, ignoring case.
- **Stats**: `GET /stats` counts rather than stores, so it cannot drift out of date.
- **Seed and reset**: `POST /reset` puts the three example tasks back.
- **Pagination**: `GET /tasks?limit=2&offset=2`, with limit capped at 100. A list endpoint with
  no cap returns more data every week it stays in production, and the day it finally times out
  it times out for every client at once.

### The mortality experiment

I added a fourth task, stopped the server, started it again and asked for `GET /tasks`. The
list was back to the three seeded tasks and the fourth was gone.

The tasks only ever existed as Python objects inside one process, so killing the process killed
the data. Any storage that has to survive a deploy, a crash or a laptop lid closing has to live
somewhere other than the program's memory, which is the argument for next week's database.

## AI vs me

Stages 0 to 6 above are hand-written. After finishing them I wrote a prompt from memory, asked
Claude to build the same API from that prompt alone, and kept its output in
[`ai-version/`](ai-version/) so my own code stays untouched. The full prompt is
[`ai-version/prompt-v1.md`](ai-version/prompt-v1.md); the generated code is
[`ai-version/main_v1.py`](ai-version/main_v1.py), 82 lines against my 117.

I ran it on port 8200 and fired my Stage 4 checkpoint curls at it. Five differences that
actually showed up:

| What I sent | Mine | AI v1 |
|---|---|---|
| `POST /tasks -d '{}'` | 400 `{"error":"title: Field required"}` | 422 `{"detail":[{"type":"missing",...}]}` |
| `POST /tasks -d '{"title":"   "}'` | 400, whitespace stripped first | 201, creates a task with a blank title |
| `GET /tasks/99` | 404 `{"error":"Task 99 not found"}` | 404 `{"detail":"Task not found"}` |
| `PUT` with only a `title`, on a task already `done:true` | stays `done:true` | silently resets to `done:false` |
| `GET /` and `GET /health` | 200 | 404, neither exists |

**What the AI did better.** It declared `response_model` on every route and stored tasks as
Pydantic `Task` objects instead of dicts. That is not decoration: my `/openapi.json` describes
the 200 response of `GET /tasks` as `{}`, an empty schema, while the AI's describes it as an
array of `Task` with typed fields, so its Swagger page documents what comes back and mine only
documents what goes in. FastAPI also validates outgoing data against `response_model`, so a
route that accidentally returned the wrong shape would fail loudly there instead of quietly
reaching the client.

**What it got wrong.** My prompt said in plain words that a missing or empty title must be
rejected with 400, and the generated code returns 422 with Pydantic's raw error list, because
`Field(min_length=1)` alone leaves FastAPI's default validation handler in place. It ignored an
explicit instruction and it looks right until you read the status code. The blank-title bug
comes from the same line: `min_length=1` counts `"   "` as three characters, so a title of
pure whitespace sails through into the list.

**What my prompt forgot.** I never said what an error body should look like, so the AI chose
FastAPI's `{"detail": ...}` and stayed consistent with it, which is a defensible answer to a
question I did not ask. I never mentioned `GET /` or `GET /health`, so they do not exist. And I
wrote "replaces the title and done", which the AI implemented literally: `done` defaults to
false on `PUT`, so updating a finished task's title marks it unfinished again. That is my
sentence being ambiguous, not the model being careless.

**The rematch.** [`ai-version/prompt-v2.md`](ai-version/prompt-v2.md) adds six sentences
covering the error envelope, the 400 mapping, whitespace stripping, the two extra endpoints,
the optional `done` on `PUT`, and response models;
[`ai-version/main_v2.py`](ai-version/main_v2.py) then matched my hand-built behaviour on every
probe above, at 116 lines against my 117. `git diff --no-index main.py ai-version/main_v2.py`
still reports 145 changed lines, but two structural choices account for most of them: it keeps
tasks as Pydantic `Task` objects where I keep plain dicts, and it has no `/stats`, `/reset`,
filtering or pagination, because prompt v2 never asked for the extras.

The thing worth keeping from this stage: the second prompt is not smarter than the first, it is
just more specific, and I could only write it because I had already built the thing by hand and
knew which six sentences were missing.

## Notes on the implementation

Validation lives in one Pydantic model, `TaskIn`, and error formatting lives in two exception
handlers, so every route answers in `{"error": "..."}` without any route repeating that logic.
FastAPI's own default for a bad body is 422; the handler maps it to the 400 this assignment
asks for.
