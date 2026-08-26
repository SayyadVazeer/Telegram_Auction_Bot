Yep — I checked the repository you pushed. Telegram_Auction_Bot repository

I also confirmed that the repo currently contains the consolidated auction model in app/database/models/auction.py, the runtime/service files, and the current handlers. 
G
GitHub
+2

One important observation: your existing PROJECT_SPEC.md is already a good foundation, but it is still more of a technical specification than a complete record of all the decisions we've made during our step-by-step build. 
G
GitHub

So I recommend adding two new files rather than replacing the existing specification.

1. PROJECT_STATUS.md

Create this in the project root:

# Telegram Auction Bot — Project Status

## 1. Project Purpose

Telegram Auction Bot is a Telegram-group-based player auction system.

The bot manages:

- One tournament per Telegram group.
- Tournament configuration.
- Teams and team owners.
- Player data imported from CSV.
- Player photos.
- Auction sets.
- Random player selection.
- Live bidding.
- Bid validation.
- Auction timers.
- Last-call sequence.
- Sold/unsold players.
- Admin auction controls.
- Tournament completion and cleanup.

The project uses:

- Python 3.12
- aiogram 3.x
- SQLAlchemy
- PostgreSQL
- Alembic
- asyncpg
- pydantic-settings
- Docker / Docker Compose

---

# 2. Core Project Rule

## One Tournament = One Telegram Group

A tournament is identified by:

`telegram_chat_id`

The database currently enforces this with a unique constraint on `Tournament.telegram_chat_id`.

Therefore:

- One Telegram group can have one tournament.
- A tournament belongs to one Telegram group.
- Auction commands must operate against the tournament belonging to the current Telegram chat.

---

# 3. Tournament Configuration

When a tournament is created, the admin provides:

- Tournament name
- Overall/base purse in Cr
- Maximum overseas/international players per team
- Maximum players per team
- Minimum bid increment in Cr

Current Tournament fields:

```text
id
telegram_chat_id
name
purse_cr
max_overseas_players
max_players_per_team
minimum_bid_increment_cr
created_at
updated_at

Important

minimum_bid_increment_cr is a floor.

It is NOT a fixed bidding step.

Example:

Current bid:

₹4.00 Cr

Minimum increment:

₹0.10 Cr

Valid:

₹4.10
₹4.25
₹4.70
₹5.00
₹8.00


Invalid:

₹4.05

4. Teams

Teams belong to a tournament.

Team fields:

id
tournament_id
name
short_code
owner_telegram_id
owner_username
logo_file_id
created_at
updated_at


Team short code:

Letters only.
Maximum length is 4 characters.
Can be 1, 2, 3, or 4 characters.
No fixed minimum length.

Examples:

C
MI
CSK
RCB

Team Owner

The admin creates/registers the team first.

The owner is assigned later.

The intended flow is:

Admin creates team.
Admin asks the owner to message the bot/admin.
Admin replies to the owner's Telegram message.
Bot uses that Telegram user as the owner of the team.
Owner can later provide the team logo/photo using the appropriate command.

Only team owners can bid.

5. Team Logo

A team can have a Telegram file_id stored as:

logo_file_id


Team information should display the logo when available.

The team information also shows:

Team name
Short code
Owner
Logo status
6. Players

Players are persistent tournament-independent data.

Player data includes:

id
player_id
name
country
role
is_overseas
set_number
base_price_cr
telegram_file_id
telegram_photo_path
created_at
updated_at

Important

Player data must NOT be deleted when a tournament is completed.

Tournament completion deletes tournament-related data only.

7. Player Base Price

The player's base price comes from:

players.base_price_cr


It must NOT be taken from the tournament purse or another temporary value.

Each player therefore has their own base price.

8. Auction Sets

set_number represents the grouping already present in the player CSV/database.

The admin starts auctions set-by-set.

When starting a set, the admin chooses:

Set number
Bid timer in seconds

The bid timer belongs to the individual auction run/session.

It is NOT a tournament setting.

9. Auction Models

Auction models are consolidated in:

app/database/models/auction.py


The project currently has:

AuctionRun
AuctionPlayer
AuctionResult

AuctionRun

Stores an individual auction session for a tournament/set.

Fields include:

id
tournament_id
set_number
bid_timer_seconds
status
started_at
paused_at
stopped_at
completed_at


The bid timer is therefore stored on the AuctionRun.

10. AuctionPlayer

Represents a player's processing inside a particular auction run.

Fields include:

id
auction_run_id
player_id
status
current_bid_cr
current_team_id
started_at
completed_at


The current highest bid is stored here.

11. AuctionResult

Stores the final result for a processed player.

Fields include:

id
tournament_id
auction_run_id
auction_player_id
player_id
result_status
winning_team_id
final_bid_cr
created_at


A player can therefore be marked:

SOLD


or

UNSOLD

12. Bid History

We do NOT need to store complete bid history.

The auction only needs the current highest bid and final result.

The intended data is:

current highest bid
current highest-bidding team
final sold price
winning team


No requirement exists to retain every individual bid.

13. Bid Commands

Owners can bid using either:

/bid 4


or:

/b 4


Decimal values are supported:

/bid 4.7
/b 4.7


All bid values are in Cr.

14. Bid Validation

A bid must pass all relevant checks.

The intended sequence is:

Telegram user
    ↓
Tournament from Telegram chat
    ↓
Team owned by user in that tournament
    ↓
Active auction player
    ↓
Bid amount valid
    ↓
Base/current bid validation
    ↓
Minimum increment floor
    ↓
Maximum team player count
    ↓
Remaining purse
    ↓
Overseas-player limit
    ↓
Accept bid

15. Atomic Bidding

Concurrent bidding must be safe.

The active AuctionPlayer row is locked during bid processing using:

.with_for_update()


This prevents two simultaneous bids from incorrectly overwriting each other.

Example:

Current = ₹4.00

Owner A → ₹5.00
Owner B → ₹4.50


If A is processed first:

A → ₹5.00 ✅
B → ₹4.50 ❌

16. Team Purse

Team purse is derived from tournament purse minus sold players.

We do NOT maintain a duplicated remaining_purse field on Team.

Conceptually:

Tournament purse
-
sum of SOLD player prices
=
remaining purse


Only SOLD players consume purse.

UNSOLD players consume nothing.

17. Maximum Players

Each team has the tournament's:

max_players_per_team


limit.

The number of players already purchased by the team is calculated from SOLD auction results.

Once the maximum is reached, further bids are rejected.

18. Overseas Players

Each tournament defines:

max_overseas_players


For an overseas player:

The team's current overseas-player count is checked.
If the maximum has already been reached, the bid is rejected.

The player flag is:

Player.is_overseas

19. Auction Player Selection

When a set is auctioned:

Select the requested set.
Exclude players already processed.
Randomly select an available player.
Start that player.
After completion, wait 5 seconds.
Randomly select another available player.
Continue until no eligible players remain.

Already processed means both:

SOLD
UNSOLD


Players that already have an auction result should not be selected again for that set.

20. Unprocessed vs Unsold

An UNSOLD player is considered processed.

Therefore:

UNSOLD
↓
processed
↓
not selected again


There is no requirement for a separate unsold re-auction system.

21. Auction Runs

The admin can run a set again if there are still eligible/unprocessed players.

The admin is not expected to run the same set more than twice, but the bot does not need to artificially enforce a two-run maximum.

The important rule is:

Allow another run while eligible players remain.

22. Bid Timer

The admin chooses the bid timer when starting an auction run.

Example:

20 seconds


The timer belongs to that AuctionRun.

It is not stored as a Tournament setting.

23. Timer Reset

When a valid bid is accepted:

current timer
    ↓
cancel
    ↓
new full bid timer


Example:

20-second timer

7 seconds elapsed
↓
valid bid
↓
reset
↓
20 seconds again

24. Last Call

When the normal bid timer expires without another valid bid, the bot enters the last-call sequence.

The exact countdown is:

10 seconds → 1
5 seconds  → 2
0 seconds  → 3 and SOLD


The final sold message remains visible for the intended short interval before the next player.

25. Bid During Last Call

If a valid bid arrives during last call:

LAST CALL
    ↓
VALID BID
    ↓
cancel last-call sequence
    ↓
normal bid timer


The auction does NOT continue with the old last-call countdown.

The new valid bid completely resets the normal bidding timer.

26. No Bids

If the player receives no valid bid:

player
 ↓
normal timer expires
 ↓
last-call sequence
 ↓
no bid
 ↓
UNSOLD


The player is then processed and excluded from future selection.

27. Auction Announcements

Every valid bid is announced in the Telegram group.

Current intended format:

🔨 BID

CSK → ₹4.70 Cr
Owner : @username
Player: Travis Head
Current highest bid: ₹4.70 Cr

Place bid to buy the player in next 20 secs...


The timer text must eventually use the active AuctionRun's bid timer instead of a hard-coded value.

28. Player Auction Announcement

When a player is selected for auction, the bot should announce the player in the group.

The player photo should be used when available.

The announcement should include the player's relevant auction information, including:

Player name
Player photo
Base price
Overseas status when useful
Current bidding state
29. Sold Announcement

When sold, the bot should be able to generate a visually polished result.

The intended design is to support an HTML template containing:

Player photo
Team logo
Player name
Team name/code
Sold price
Owner information where appropriate


This is intended for the final sold presentation.

30. Unsold Announcement

UNSOLD players should also show the player's photo when available.

31. Admin Auction Controls

Admin must be able to:

Start an auction for a selected set.
Choose the bid timer.
Pause the auction.
Resume the auction.
Stop the auction.
Pause

Pause is allowed even while an active player's bidding timer is running.

Pause must preserve the auction/player state.

32. Stop

Stop is NOT allowed while an active player's bidding is running.

If the player is currently accepting bids:

STOP → rejected


Pause is still allowed.

33. Resume

Resume continues the selected auction run.

It must not reset already processed players.

The auction continues with the remaining eligible players.

34. Auction Completion

When all eligible players from the selected set have been processed:

Auction is ended for the selected set.


The bot should announce that the selected set has finished.

35. Tournament Completion

The admin has a tournament completion command.

The command must request confirmation.

The bot generates a random 4-digit confirmation code.

The admin must enter/confirm the correct code.

After successful confirmation:

Tournament data → deleted
Player data → preserved


Player records must never be deleted by tournament completion.

36. Admin Panel

The admin panel contains a Players button.

The exact functionality of the Players button will be implemented later.

Do not assume or invent its final behavior until that step is reached.

37. Team Information

Team information should display:

Team name
Short code
Owner
Team logo


Future team information can additionally include:

Players purchased
Player count
Remaining purse
Overseas player count


These were identified as still-needed functionality.

38. Time Handling

Auction timers are runtime timers and are based on elapsed seconds.

Tournament/auction timestamps should be handled consistently.

User-facing scheduled times, if later introduced, should be presented in the appropriate Telegram/user context rather than blindly displaying UTC.

39. Current Architecture

Current major structure:

Telegram
   ↓
aiogram handlers
   ↓
Services
   ↓
SQLAlchemy
   ↓
PostgreSQL


Current important service files:

app/services/auction_service.py
app/services/auction_runtime.py
app/services/tournament_service.py


Auction models are consolidated in:

app/database/models/auction.py

40. Completed Work

The following areas have been implemented and tested during development:

Admin access
Tournament creation
Tournament configuration
One tournament per Telegram group
Tournament database model
Team creation
Team short-code validation
Team owner handling
Team information
Team logo upload/storage
Player model/data handling
Player base price storage
Auction database models
Alembic auction migration
Bid command
/bid
/b
Decimal Cr bid parsing
Bid validation foundation
Tournament-specific owner lookup
Team eligibility validation foundation
Atomic bid row locking
Auction runtime state foundation
Normal timer foundation
Project compilation checks

The project has repeatedly passed:

python -m compileall app

41. Currently In Progress

The auction engine is currently being built.

The next major functionality is:

Admin starts set
↓
Admin enters bid timer
↓
AuctionRun created
↓
Random player selected
↓
Player announcement
↓
Timer starts
↓
Bids reset timer
↓
Timer expires
↓
Last call
↓
Sold/Unsold
↓
Next random player

42. Remaining Major Work

Still to implement/integrate:

Complete admin start-set auction flow
Set selection UI/commands
Bid timer input UI/command
AuctionRun lifecycle
AuctionPlayer lifecycle
Player announcement
Player photo announcement
Timer connected to active AuctionRun
Timer reset after valid bid
Last-call sequence
Last-call cancellation on valid bid
SOLD finalization
UNSOLD finalization
5-second transition between players
Random next-player selection
Pause
Resume
Stop restrictions
Set completion announcement
Team purse display
Team player list
Team player count
Overseas count display
Final sold HTML presentation
Team logo in sold presentation
Player photo in sold presentation
Tournament completion command
Tournament deletion confirmation
Admin Players panel functionality
Full auction integration testing
Concurrency testing
Restart/recovery behavior
Final cleanup/refactoring
Automated tests
43. Development Method

This project is intentionally being developed incrementally.

Each step should:

Explain what is being added.
Identify exact files to modify.
Give the exact code/change.
Run a compile check.
Test the behavior when appropriate.
Confirm success.
Move to the next small step.

Do not dump a huge amount of code at once.

44. Current Development Rule

Before making changes:

Inspect the existing code.
Reuse existing models/services.
Do not create duplicate models.
Do not create duplicate database fields.
Do not change confirmed business rules without asking.
Keep database data and runtime state separate.
Keep Telegram handlers reasonably thin.
Put business logic in services.
Compile after meaningful changes.
45. Current Next Step

The next implementation target is:

Connect AuctionRun creation → random player selection → AuctionPlayer activation → player announcement → runtime timer.

After that:

Connect valid /bid → timer reset.

Then:

Implement last-call → SOLD/UNSOLD → next player.


# 2. `AI_CONTEXT.md`

This is the one I especially want you to keep. It tells a future AI **how we work**, not just what the bot does.

```md
# Telegram Auction Bot — AI Development Context

## IMPORTANT

This document is the working context for AI-assisted development of this project.

The project is being developed collaboratively and incrementally.

The user explicitly wants to work:

**STEP BY STEP.**

Do NOT implement the entire remaining project in one response.

Do NOT jump several steps ahead.

Every implementation should be handled as a small numbered step.

---

# 1. Development Style

The user wants this workflow:

```text
Discuss requirement
        ↓
Confirm requirement
        ↓
Identify exact files
        ↓
Make one small change
        ↓
Run compile/test
        ↓
User confirms
        ↓
Next step


The AI should normally:

Ask for missing information when necessary.
Inspect existing code before suggesting structural changes.
Give exact file paths.
Give exact code changes.
Explain briefly what the change does.
Ask the user to run the relevant command.
Wait for confirmation before moving to the next substantial step.

Do not overwhelm the user with a complete rewrite.

2. Never Guess Existing Code

Before creating:

a new model
a new database field
a new service
a new handler
a new migration

check whether the functionality already exists.

The user has repeatedly built functionality step-by-step.

Existing code may already contain part of the requested behavior.

If uncertain, ask the user to paste the relevant file or inspect the repository.

3. Project Identity

This is a Telegram player auction bot.

The auction runs inside Telegram groups.

The primary relationship is:

Telegram Group
      ↓
Tournament
      ↓
Teams
      ↓
Auction Runs
      ↓
Players

4. One Tournament Per Telegram Group

The tournament is identified by:

telegram_chat_id


Tournament.telegram_chat_id is unique.

Never design the system around multiple tournaments inside the same Telegram group unless the user explicitly changes this requirement.

5. Technology

Use the existing stack:

Python 3.12
aiogram 3.x
SQLAlchemy
PostgreSQL
Alembic
asyncpg
pydantic-settings
Docker
Docker Compose


Do not introduce another framework unnecessarily.

6. Existing Model Files

Models are currently organized as:

app/database/models/
├── auction.py
├── player.py
├── team.py
├── tournament.py
└── __init__.py


Auction models are consolidated in:

app/database/models/auction.py


It contains:

AuctionRun
AuctionPlayer
AuctionResult


Do NOT create:

auction_run.py
auction_player.py
auction_result.py


unless the user explicitly decides to reorganize the models.

7. Tournament Model

Current important fields:

telegram_chat_id
name
purse_cr
max_overseas_players
max_players_per_team
minimum_bid_increment_cr


The tournament purse is the overall purse available to each team.

The same tournament rules apply to every team.

8. Team Model

Current important fields:

tournament_id
name
short_code
owner_telegram_id
owner_username
logo_file_id


Do not add a duplicated remaining-purse field unless explicitly requested.

Team purse should be calculated from tournament purse and SOLD results.

9. Player Model

Current important fields:

player_id
name
country
role
is_overseas
set_number
base_price_cr
telegram_file_id
telegram_photo_path


The player's base price MUST come from:

player.base_price_cr


Do not use tournament purse as player base price.

10. Player Sets

Player.set_number is the set/grouping imported from the CSV.

The admin auctions one set at a time.

The admin chooses:

set_number
bid_timer_seconds

11. AuctionRun

An AuctionRun represents one auction session for a tournament/set.

Important fields:

tournament_id
set_number
bid_timer_seconds
status
started_at
paused_at
stopped_at
completed_at


IMPORTANT:

bid_timer_seconds belongs to the AuctionRun.

It is NOT a Tournament setting.

12. AuctionPlayer

An AuctionPlayer represents a player being processed in an AuctionRun.

Important fields:

auction_run_id
player_id
status
current_bid_cr
current_team_id
started_at
completed_at


It stores the current highest bid.

13. AuctionResult

AuctionResult represents the final result.

Important fields:

tournament_id
auction_run_id
auction_player_id
player_id
result_status
winning_team_id
final_bid_cr


Results can be:

SOLD
UNSOLD

14. No Bid History

The user explicitly does NOT want full bid history.

Do not add:

Bid table
BidHistory table
Bid event log


unless explicitly requested later.

The important information is:

current highest bid
current team
final bid
winning team

15. Bid Commands

Both commands are supported:

/bid 4
/b 4


Decimal Cr values are supported:

/bid 4.7
/b 4.7

16. Who Can Bid

Only registered team owners can bid.

The owner must own a team belonging to the tournament associated with the current Telegram group.

Do NOT only search by:

owner_telegram_id


without also filtering by:

tournament_id


The correct conceptual lookup is:

message.chat.id
      ↓
Tournament
      ↓
user Telegram ID
      ↓
Team in that tournament

17. Bid Amount Rules

Bids are in Cr.

Bids must be positive.

The minimum bid increment is a FLOOR.

It is not a fixed increment.

Example:

Current = 4.00
Minimum increment = 0.10


Then:

4.10 ✅
4.20 ✅
4.70 ✅
5.50 ✅


The bidder may jump by any amount.

18. Atomic Bidding

Concurrent bids are expected.

The active AuctionPlayer row should be locked during bid validation/update.

The existing implementation uses:

.with_for_update()


Do not remove this protection.

19. Team Purse Rules

Every team starts with:

Tournament.purse_cr


Spent purse is calculated from SOLD results.

Concept:

remaining purse =
tournament purse - sum(SOLD final bids)


Only SOLD players consume purse.

UNSOLD players consume zero purse.

20. Maximum Players

Use:

Tournament.max_players_per_team


Count SOLD players belonging to the team.

Reject a bid if the team has already reached the maximum.

21. Overseas Limit

Use:

Player.is_overseas


Tournament setting:

Tournament.max_overseas_players


If the player is overseas, count the team's already SOLD overseas players.

Reject if the limit is already reached.

22. Player Selection

When starting an auction for a set:

filter by set_number
        ↓
exclude already processed players
        ↓
random selection


A player with an AuctionResult is considered processed.

Therefore:

SOLD → processed
UNSOLD → processed


Neither should be selected again.

23. Running a Set Again

The same set can be auctioned again if eligible/unprocessed players remain.

Do not impose an artificial two-run restriction.

The user said the admin will not normally run the same set more than twice, so there is no need to enforce that limit.

24. Random Order

Players are selected randomly.

The bot must not simply process the CSV order unless the user later changes this requirement.

25. Auction Timer

The admin chooses the bid timer when starting the auction run.

Example:

20 seconds


Every valid bid resets the timer to the full selected duration.

Example:

20 seconds
 ↓
7 seconds elapsed
 ↓
valid bid
 ↓
timer reset to 20 seconds

26. Runtime Timer State

Live asyncio timer tasks should NOT be stored in PostgreSQL.

Persistent auction data belongs in the database.

Live timer/task state belongs in runtime memory.

Current runtime foundation:

app/services/auction_runtime.py

27. Last Call

Normal timer expiration triggers:

10 seconds → 1
5 seconds  → 2
0 seconds  → 3 and SOLD


The final sequence must not continue if a valid bid arrives.

28. Bid During Last Call

A valid bid during last call means:

cancel last call
      ↓
accept bid
      ↓
return to normal bid timer
      ↓
full timer duration


This is a confirmed business rule.

Do not change it.

29. No Bid

If there are no bids through the entire process:

normal timer
 ↓
last call
 ↓
no bid
 ↓
UNSOLD


The player becomes processed.

30. SOLD

If there is a valid highest bid when the final countdown completes:

AuctionResult
result_status = SOLD
winning_team_id = current_team
final_bid_cr = current_bid


Then:

wait 5 seconds
 ↓
next random player

31. UNSOLD

If no valid bid exists:

AuctionResult
result_status = UNSOLD
winning_team_id = NULL
final_bid_cr = NULL


Then:

wait 5 seconds
 ↓
next random player

32. Player Announcement

The player should be announced with their Telegram photo when available.

The announcement should show relevant player information.

The bot should use:

telegram_file_id


when available rather than unnecessarily re-uploading the same Telegram image.

33. Bid Announcement

Every valid bid must be announced in the group.

Target format:

🔨 BID

CSK → ₹4.70 Cr
Owner : @username
Player: Travis Head
Current highest bid: ₹4.70 Cr

Place bid to buy the player in next 20 secs...


The timer value must eventually be dynamic.

Do NOT hard-code 20 once the AuctionRun timer is connected.

34. Sold Presentation

The user wants a polished HTML-based visual sold presentation.

It should eventually support:

Player photo
Team logo
Player name
Team
Sold price


Do not implement an unrelated templating architecture without first discussing it.

35. Unsold Presentation

UNSOLD should also display the player photo when available.

36. Pause

Admin can pause the auction even while an active player's bid timer is running.

Pause must preserve state.

Do not mark the current player as processed merely because the auction was paused.

37. Resume

Resume continues the same auction run.

Already processed players remain processed.

The auction should continue with the remaining eligible players.

38. Stop

Stop is NOT allowed while an active player's bidding is running.

Therefore:

ACTIVE PLAYER
+
BIDDING RUNNING
+
STOP
=
REJECT


Pause remains allowed.

39. Set Completion

When all eligible players in the selected set have been processed:

Auction is ended for the selected set.


The bot should send this announcement to the group.

40. Tournament Completion

The admin can complete/delete a tournament using the tournament-completion command.

The command must:

Ask for confirmation.
Generate a random 4-digit code.
Require the admin to confirm using the code.
Delete tournament-related data.
Preserve Player records.

NEVER delete the persistent Player table as part of tournament completion.

41. Team Information

Team information should eventually display:

Team
Owner
Logo
Player count
Players
Remaining purse
Overseas count


Player list/count functionality has not yet been completed.

42. Admin Players Button

The admin panel contains a Players button.

Its final functionality is intentionally deferred.

Do not invent functionality for this button before the user asks to implement that part.

43. Existing Important Files

Current known files:

app/
├── bot/
│   ├── bot.py
│   └── handlers/
│       ├── bidding.py
│       ├── start.py
│       ├── team.py
│       └── tournament.py
│
├── database/
│   ├── base.py
│   ├── session.py
│   └── models/
│       ├── auction.py
│       ├── player.py
│       ├── team.py
│       └── tournament.py
│
├── services/
│   ├── auction_runtime.py
│   ├── auction_service.py
│   └── tournament_service.py
│
└── ...


Repository also contains:

data/
migrations/
scripts/
PROJECT_SPEC.md
Prompt.md
README.md

44. Database Migration Rule

The project uses Alembic.

After model changes:

alembic revision --autogenerate -m "description"


then:

alembic upgrade head


Do not create migrations for purely runtime Python state.

45. Compilation Rule

After meaningful code changes run:

python -m compileall app


A clean result is expected before proceeding.

46. AI Must Work Step-by-Step

This is a hard requirement.

The user wants development to continue in numbered steps.

Example:

Step 176
Step 177
Step 178
...


For each step:

Explain the purpose.
Tell exactly which file to open.
Tell exactly what to add/change.
Avoid unrelated refactoring.
Ask the user to compile/test.
Wait for the result.
Then continue.

Do not jump from Step 176 directly to a complete auction implementation.

47. AI Must Preserve Confirmed Decisions

Do not silently change these decisions:

One tournament per Telegram group.
telegram_chat_id identifies the tournament group.
Bid timer belongs to AuctionRun, not Tournament.
Only team owners can bid.
/bid and /b are both valid.
Bids are in Cr.
Minimum increment is a floor.
Bidders may jump by any amount.
Player base price comes from Player.base_price_cr.
Same tournament rules apply to all teams.
No complete bid history is required.
Highest/current bid is sufficient.
Players are selected randomly within a set.
Processed players are excluded.
SOLD and UNSOLD both count as processed.
Valid bid during last call cancels last call.
Valid bid restarts the normal timer.
Last-call points are 10 seconds, 5 seconds, and 0 seconds.
Pause is allowed during active bidding.
Stop is not allowed while active bidding is running.
Five seconds between processed players.
Player photo should be shown.
Unsold player should show photo.
Sold presentation should support player photo and team logo.
Tournament completion requires a random 4-digit confirmation.
Tournament completion deletes tournament data but preserves player data.

If a new requirement conflicts with one of these, ask the user before changing the existing behavior.

48. Avoid Premature Refactoring

Do not refactor working code merely because another architecture might be cleaner.

The current goal is to finish functionality safely.

Refactoring can happen after the auction engine is working.

49. Avoid Duplicate Logic

Before adding a method:

Search the existing project.

For example, before adding:

get_team_by_owner


check whether it already exists.

Before adding auction models, check:

app/database/models/auction.py


Before adding auction runtime logic, check:

app/services/auction_runtime.py

50. Current Development Position

The project has completed the foundation through the current bidding/runtime work.

The current immediate goal is:

AuctionRun
   ↓
select set
   ↓
random player
   ↓
AuctionPlayer ACTIVE
   ↓
player announcement
   ↓
timer
   ↓
bid
   ↓
timer reset
   ↓
last call
   ↓
SOLD / UNSOLD
   ↓
next player


The next step should focus only on the next missing piece rather than implementing everything above at once.

51. Current Next Step

Before writing more auction code:

Inspect the existing auction-related handlers/services and determine whether AuctionRun creation already exists.

If it already exists:

reuse it
do not create a duplicate implementation

If it does not exist:

implement AuctionRun creation first.

Then proceed incrementally toward:

AuctionRun creation
→ random player
→ AuctionPlayer activation
→ player announcement
→ timer
→ bid timer reset
→ last call
→ result finalization
→ next player

52. Communication Style

Keep explanations practical.

The user is actively editing files and running PowerShell commands.

Prefer:

Open this file:
...
Replace this:
...
With:
...
Run:
...


rather than large theoretical explanations.

When a compile/test succeeds, acknowledge it and move to the next numbered step.

If a runtime error occurs:

Diagnose the exact error.
Explain why.
Give the smallest fix.
Compile again.
Continue.
53. Most Important Instruction

Work with the user, not ahead of the user.

The project is intentionally being built one confirmed step at a time.

Do not assume a feature is wanted merely because it would be useful.

Ask when requirements are unclear.

Preserve confirmed decisions.

Inspect existing code before creating new code.

And always continue from the project's actual current state.


## One thing I noticed from the repo

Your existing `PROJECT_SPEC.md` already documents the architecture and technology stack, including Python 3.12, aiogram, SQLAlchemy, PostgreSQL, Alembic and the handler/service separation. 
G
GitHub



The repository currently shows the auction models consolidated in `auction.py` and the runtime/service files we have been working on. 
G
GitHub
+1



So **don't delete `PROJECT_SPEC.md` or `Prompt.md`**. Keep them, and add:

```text
PROJECT_STATUS.md
AI_CONTEXT.md


I especially recommend keeping AI_CONTEXT.md in the repo because when you open a fresh AI coding session later, you can simply say:

"Read AI_CONTEXT.md first. Work on this project step-by-step from the current state. Do not skip steps."

That should make the future sessions much more consistent with how we've been developing this bot.

G
Sources
