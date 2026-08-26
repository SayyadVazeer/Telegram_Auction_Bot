Absolutely. At this point, it makes sense to create a living project specification so we don't lose the decisions we've made as the bot grows.

Create a file in your project root:

PROJECT_SPEC.md


Paste the following into it:

# Telegram Auction Bot — Project Specification

## 1. Project Overview

This project is a Telegram-based player auction system designed to run an auction inside a Telegram group.

The system will manage:

- Tournaments
- Tournament-specific auction rules
- Teams
- Team owners
- Players
- Player photos
- Auction sets
- Random player selection
- Live bidding
- Bid timers
- Last-call sequence
- Sold/unsold players
- Auction history
- Admin controls
- Tournament completion

The bot is designed to support concurrent bidding and future expansion without mixing Telegram handlers, business logic, and database operations.

---

# 2. Technology Stack

## Backend

- Python 3.12
- aiogram 3.x
- SQLAlchemy
- PostgreSQL
- Alembic
- asyncpg
- pydantic-settings

## Infrastructure

- Docker
- Docker Compose
- Persistent PostgreSQL storage
- Local/player-photo storage during development

## Telegram

The bot runs inside Telegram groups.

A tournament is associated with one Telegram group.

---

# 3. Project Architecture

The intended architecture is:

```text
Telegram
   |
   v
aiogram
   |
   v
Handlers
   |
   v
Services
   |
   v
Repositories
   |
   v
SQLAlchemy
   |
   v
PostgreSQL


Handlers should not directly contain complicated database/business logic.

The intended responsibility is:

Handler
    ↓
Service
    ↓
Repository
    ↓
Database


This allows the auction logic to eventually be reused by other interfaces if required.

4. Project Structure

Current/target structure:

Telegram_Auction_Bot/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── player.py
│   │       ├── tournament.py
│   │       └── team.py
│   │
│   ├── repositories/
│   │   ├── player_repository.py
│   │   ├── tournament_repository.py
│   │   └── team_repository.py
│   │
│   ├── services/
│   │   ├── player_service.py
│   │   ├── tournament_service.py
│   │   ├── team_service.py
│   │   ├── auction_service.py
│   │   └── bidding_service.py
│   │
│   └── bot/
│       ├── bot.py
│       │
│       ├── handlers/
│       │   ├── start.py
│       │   ├── players.py
│       │   ├── tournament.py
│       │   ├── team.py
│       │   ├── auction.py
│       │   ├── bidding.py
│       │   └── admin.py
│       │
│       ├── keyboards/
│       │   ├── tournament.py
│       │   ├── team.py
│       │   ├── auction.py
│       │   └── admin.py
│       │
│       └── states/
│           ├── tournament_states.py
│           ├── team_states.py
│           └── auction_states.py
│
├── data/
│   ├── csv/
│   │   └── players.csv
│   │
│   └── photos/
│       ├── PLY0001.jpg
│       ├── PLY0002.jpg
│       └── ...
│
├── migrations/
│
├── scripts/
│   ├── import_players.py
│   └── validate_players.py
│
├── tests/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
└── PROJECT_SPEC.md

5. Player Data

The player CSV is already cleaned and validated.

The existing player identifier is:

player_id


Example:

PLY0001
PLY0002
PLY0003


No additional player code needs to be generated.

The original CSV column was called payer_id, but it represents the player's unique identifier and has been treated as:

player_id

6. Player Fields

The player data contains:

player_id
name
country
role
is_overseas
set_number
base_price_cr


Database player records additionally contain Telegram/photo-related fields.

Current concept:

Player
├── id
├── player_id
├── name
├── country
├── role
├── is_overseas
├── set_number
├── base_price_cr
├── telegram_file_id
├── telegram_photo_path
├── created_at
└── updated_at


There is intentionally NO is_active column.

The player record is permanent master data.

7. Player ID

player_id is unique.

Example:

PLY0001


The database should enforce uniqueness.

Player IDs must never be reused for a different player.

8. Player Photos

Player photos are initially stored locally:

data/photos/


Example:

data/photos/PLY0001.jpg
data/photos/PLY0002.jpg


When a player photo is first sent through Telegram, Telegram returns a file_id.

The bot stores that file_id.

Preferred photo delivery:

Player
   |
   +--> telegram_file_id
            |
            v
        Telegram


Fallback:

No telegram_file_id
        |
        v
Check telegram_photo_path
        |
        v
Upload photo to Telegram
        |
        v
Save returned file_id


This prevents repeated uploads.

9. Tournament Concept

A tournament belongs to exactly one Telegram group.

Conceptually:

Telegram Group
      |
      v
Tournament


One group should not run multiple active tournaments simultaneously.

Tournament data contains the rules that are common to all teams participating in that tournament.

10. Tournament Fields

When an admin creates a tournament, the following must be entered:

Tournament Name
Overall Base Purse
International Players Maximum Limit
Maximum Players Per Team
Minimum Bid Increment


These values apply to all teams in the tournament.

11. Tournament Purse

The tournament has an overall/base purse value.

Example:

Overall Base Purse:
₹100 Cr


Every registered team starts with the same purse.

The team does not have an independently configured starting purse.

The team's remaining purse will eventually be calculated from:

Tournament Base Purse
-
Total Player Purchases
=
Remaining Purse

12. International Player Limit

The tournament specifies the maximum number of overseas/international players that each team may acquire.

Example:

International Players Max:
8


This is a tournament rule and applies equally to every team.

13. Maximum Players Per Team

The tournament specifies the maximum number of players each team can acquire.

Example:

Maximum Players Per Team:
20


This applies equally to all teams.

14. Minimum Bid Increment

The tournament specifies the minimum bid increment.

Important:

The minimum increment is a FLOOR, NOT a fixed bid step.

Example:

Minimum Bid Increment:
₹0.10 Cr


If the current bid is:

₹4.70 Cr


then a bid of:

₹4.80 Cr


is valid.

But a bidder can jump higher by any amount:

₹5.20 Cr
₹6.00 Cr
₹10.00 Cr


provided the bid is at least the current bid plus the minimum increment.

The bot must NOT force bids to follow fixed increments.

15. Tournament Creation

Tournament creation is admin-only.

The bot uses an FSM conversation.

The admin enters:

Tournament Name
        ↓
Overall Base Purse
        ↓
International Player Maximum
        ↓
Maximum Players Per Team
        ↓
Minimum Bid Increment
        ↓
Confirmation
        ↓
Create


The confirmation screen supports editing individual fields.

An editing state flag is used to distinguish:

Normal creation


from:

Editing an existing value


After an edited value is entered, the bot returns to the confirmation screen rather than continuing through the entire creation flow.

16. Tournament Completion

Admin can use:

/tournament_completed


The bot must ask for confirmation.

It generates a random 4-digit confirmation code.

The admin must enter the correct code.

Only after successful confirmation:

Tournament data is deleted


Player master data is NOT deleted.

This means:

Tournament data → deleted
Player data     → retained


Auction history associated with the tournament is expected to be deleted as part of tournament completion unless the future data-retention design changes this.

17. Team Concept

Teams belong to tournaments.

Tournament
    |
    +--- Team
    +--- Team
    +--- Team


There is no fixed maximum number of teams.

A tournament can have:

1 team
2 teams
3 teams
4 teams
5 teams
...

18. Team Fields

Current team model:

Team
├── id
├── tournament_id
├── name
├── short_code
├── owner_telegram_id
├── owner_username
├── logo_file_id
├── created_at
└── updated_at


There is intentionally no team-specific purse or player-limit configuration.

Those values come from the tournament.

19. Team Name

Team names must be unique within a tournament.

Example:

Chennai Super Kings


The same name can exist in another tournament.

20. Team Short Code

Team short code rules:

2 to 4 characters
Letters only
Automatically converted to uppercase


Valid:

CS
CSK
TEAM
MI
RCB


Invalid:

C
CSK1
C-K
C.S.K
CSKS1


The short code must be unique within the tournament.

21. Team Creation

Admin creates a team using the team-management flow.

The bot asks for:

Team Name
Short Code


It does NOT ask for:

Owner
Logo
Purse
Maximum Players
Overseas Limit


Those are handled separately.

Confirmation screen:

🏏 New Team

Team Name: Chennai Super Kings
Short Code: CSK

Owner: Not assigned
Logo: Not uploaded

[ Create ]
[ Edit ]
[ Cancel ]

22. Team Owner Assignment

Owner assignment is performed by an admin.

The admin does NOT manually type the owner's Telegram ID.

The intended flow is:

Owner sends a message
        ↓
Admin replies to owner's message
        ↓
Admin sends:

/assign_owner CSK
        ↓
Bot identifies reply_to_message.from_user
        ↓
Bot assigns that Telegram user to CSK


Example:

Owner:
Hello, I want to manage CSK.

Admin replies:

/assign_owner CSK


The bot stores:

owner_telegram_id
owner_username


The Telegram numeric ID is the actual identity.

The username is for display/tagging.

23. Owner Assignment Rules

Within one tournament:

A team can have only one owner.
One Telegram user can own only one team.
A team with an owner cannot accidentally be reassigned.
A user who already owns another team cannot be assigned to another team.

Ownership is tournament-specific.

The same Telegram user may own different teams in different tournaments.

24. Team Logo

A team owner can upload the team logo.

Command:

/team_logo


The bot verifies:

Is this Telegram user the owner of a team?


If yes:

Bot asks for photo
        ↓
Owner sends photo
        ↓
Bot saves Telegram file_id


The field is:

logo_file_id


The owner can replace the existing logo by using /team_logo again.

The current implementation stores Telegram's file_id rather than maintaining a local team-logo directory.

25. Team View

Admin can view teams registered in the tournament.

Current basic team information:

Team Name
Short Code
Owner
Logo status


Future team information will include:

Remaining Purse
Players Purchased
Maximum Players
Overseas Players
Overseas Maximum
Player Roster


These values should be derived from auction/purchase records rather than duplicated unnecessarily in the team table.

26. Auction Concept

Auction functionality will be built after tournament and team foundations.

The auction is tournament-specific.

Auction runs are also set-specific.

The auction does NOT permanently store the bid timer as a tournament setting.

27. Auction Sets

The existing set_number in the player CSV represents the player's auction grouping.

Example:

Set 1
Set 2
Set 3
...


The admin starts an auction set manually.

Admin chooses:

Set
Bid Timer


The bid timer belongs to that particular auction run/session.

28. Starting a Set Auction

Admin selects a set.

Example:

Start Set 3
Bid Timer: 20 seconds


The bot:

Finds players in the selected set who have not yet been processed.
Randomly selects one player.
Starts that player's auction.
When sold, waits 5 seconds.
Randomly selects another unprocessed player.
Continues until no eligible players remain.

Players already processed in previous runs of the same set are excluded.

29. Multiple Runs of the Same Set

The same set may be auctioned again.

The bot should NOT reset previously processed players.

Example:

First run:

Set 1
45 players
15 processed


Second run:

35 remaining players


The bot randomly chooses only from those 35.

The admin may run a set again as long as there are remaining unsold/unprocessed players.

There is no need to strictly limit the admin to two runs.

30. Unprocessed vs Sold

Players that have already been processed are excluded from later random selection.

A player that receives no valid bid is considered unsold/unprocessed for the purpose of future auction runs.

There is no separate "unsold auction" system required.

If players remain in the set, the admin can run the set again.

Once all players in the selected set have been processed, the bot sends:

Auction ended for the selected set.

31. Player Auction Start

When a player is selected randomly, the bot displays the player's information and starts bidding.

The player's base price comes directly from:

players.base_price_cr


The bot must NOT ask the admin to enter the player's base price.

32. Bidding Rules

Only team owners can bid.

Bids are placed manually using:

/bid 4


or:

/bid 4.7


Amounts are in Crores.

Example:

/bid 4.7


means:

₹4.70 Cr


The bot validates:

User is a registered team owner.
The owner belongs to a team in the active tournament.
The team has enough remaining purse.
The bid is greater than the current bid by at least the minimum bid increment.
The player is currently open for bidding.
The team is allowed to purchase the player according to tournament rules.
33. Bid Announcement

Every valid bid is immediately announced in the Telegram group.

Target format:

🔨 BID

CSK → ₹4.70 Cr
Owner : @username
Player: Travis Head
Current highest bid: ₹4.70 Cr

Place bid to buy the player in next 20 secs...


The exact formatting can be refined later.

34. Bid Timer

When an auction begins, the admin chooses the bid timer.

Example:

20 seconds


The timer is NOT stored as a tournament-wide setting.

It belongs to the active auction/set session.

Every valid bid resets the timer.

Example:

20 sec
   ↓
Bid received
   ↓
Reset to 20 sec
   ↓
Another bid
   ↓
Reset to 20 sec

35. Last Call

When the bid timer reaches the final stage without another bid, the bot enters the last-call sequence.

The last-call timings are:

10 seconds → "1"
5 seconds  → "2"
0 seconds  → "3 and SOLD"


The bot must identify the current highest bidder/team.

The final sequence lasts only once.

36. New Bid During Last Call

If a valid bid is received during the last-call sequence:

Last Call
    ↓
Valid bid
    ↓
Immediately cancel last-call sequence
    ↓
Accept new bid
    ↓
Return to normal bid timer


The timer resets to the configured auction bid timer.

The same process continues again.

37. Sold Sequence

If no valid bid is received during the last-call period:

10 sec → 1
5 sec  → 2
0 sec  → 3 and SOLD


The player is sold to the current highest bidder.

The purchase is permanently recorded.

The team's remaining purse will reflect the purchase.

After the player is sold:

Wait 5 seconds
        ↓
Randomly select next player

38. Player Sold Data

Auction/purchase records should preserve historical information.

A player should NOT be overwritten to represent only the latest auction.

For example:

Tournament 2027
Travis Head → CSK → ₹4.70 Cr

Tournament 2028
Travis Head → RCB → ₹7.00 Cr


The player master record remains unchanged.

The auction/purchase tables represent the tournament-specific result.

39. Auction Pause

Admin can pause an active auction.

Pause is allowed even when a player's bid timer is currently running.

When paused:

Auction progression stops.
Timer progression stops.
No automatic player transition occurs.
Current auction state must be preserved.

The admin can resume later.

40. Auction Resume

When the admin resumes:

Pause
  ↓
Resume
  ↓
Continue current auction state


The auction does not reset.

If the current player was active when paused, the system should resume the appropriate active bid state according to the implementation.

41. Auction Stop

Admin can stop the auction.

However:

Stop cannot be used while an active bid for the current player is running.

This prevents accidentally abandoning an active player's bidding process.

Stop is different from pause.

Pause:

Temporary
Can resume


Stop:

Ends the current auction run
Does not reset players already sold/processed

42. Stop Does Not Reset Sold Players

If:

Set 1
45 players
15 processed


and admin stops the auction:

15 remain processed
30 remain available


The processed players remain processed.

Starting Set 1 again randomly chooses only from the remaining eligible players.

43. Auction Completion

When no unprocessed players remain in the selected set:

🏁 Auction ended for the selected set.


The auction session ends.

44. Admin Controls

The admin panel will eventually contain controls for:

Players
Tournament
Teams
Auction


Additional controls will be added as the relevant modules are implemented.

The Players button exists in the admin panel, but its detailed purpose will be defined later during the player-management portion.

45. Admin Security

Only configured Telegram administrators may access admin functions.

Admin IDs are configured through environment/configuration settings.

Example:

ADMIN_IDS=123456789,987654321


Admin-only actions include:

Tournament creation
Tournament editing
Tournament completion
Team registration
Owner assignment
Auction control
Pause
Resume
Stop
Set selection
46. Database Principles

The database should preserve separation between:

Master data
Players


and:

Tournament data
Tournaments
Teams
Auctions
Bids
Purchases


A player can participate in multiple tournaments.

The player master record must not be overwritten by auction results.

47. Expected Future Database Structure

Target conceptual structure:

                    TOURNAMENT
                         |
              +----------+----------+
              |                     |
              v                     v
            TEAMS                 AUCTIONS
              |                     |
              |               +-----+------+
              |               |            |
              v               v            v
          OWNERS            PLAYERS       BIDS
                                  |
                                  |
                              PURCHASES


The exact relational implementation will be finalized before auction coding.

48. Team Roster and Purse

The team table should NOT contain duplicated values such as:

player_count
remaining_purse
overseas_count


unless there is a strong performance/reliability reason later.

These can be calculated from purchase records:

Starting Purse
    -
Sum of purchases
    =
Remaining Purse


and:

Number of purchases
    =
Player Count


and:

Overseas purchases
    =
Overseas Player Count


This avoids inconsistent data.

49. Current Completed Features

At this stage the following are completed and working:

Project foundation
Python environment
Docker setup
PostgreSQL
SQLAlchemy
Alembic
Player database
Player CSV validation/import foundation
Admin access
Tournament creation
Tournament editing
Tournament configuration
Tournament completion confirmation flow
Team database model
Team creation
Team name validation
Team short-code validation
Team listing
Team detail view
Team owner assignment
Team owner uniqueness protection
Team logo upload
Telegram team logo file_id storage
50. Current Team Flow

The current team flow is:

Admin
  |
  v
Add Team
  |
  +--> Team Name
  |
  +--> Short Code
  |
  v
Confirmation
  |
  v
Create
  |
  v
PostgreSQL


Owner:

Owner sends message
       |
       v
Admin replies
       |
       v
/assign_owner CSK
       |
       v
Owner assigned


Logo:

Owner
  |
  v
/team_logo
  |
  v
Send photo
  |
  v
Telegram file_id
  |
  v
teams.logo_file_id

51. Important Design Decisions

These decisions should not be changed accidentally during future implementation.

Player ID

Use the existing:

player_id


No second player identifier.

Player active flag

Do NOT add:

is_active


unless explicitly reconsidered later.

Tournament/group relationship

One tournament belongs to one Telegram group.

Team count

No fixed maximum number of teams.

Team short code
2–4 letters
Uppercase
Unique per tournament

Team owner

Owner is assigned by admin reply:

/assign_owner CSK

Team logo

Uploaded by the team owner using:

/team_logo

Tournament rules

These apply equally to all teams.

Bid increment

Minimum floor, not fixed stepping.

Bid entry

Manual command:

/bid 4
/bid 4.7

Bid timer

Configured per auction/set run, not tournament-wide.

Bid reset

Every valid bid resets the timer.

Last call
10 sec → 1
5 sec  → 2
0 sec  → 3 and SOLD

Last-call bid

A valid bid immediately cancels last call and restarts the normal timer.

Auction selection

Players are randomly selected from remaining unprocessed players in the selected set.

Pause

Allowed during an active player bid.

Stop

Not allowed while an active player bid is running.

Stop behavior

Does not reset previously processed/sold players.

Tournament completion

Deletes tournament data, not player master data.

52. Development Philosophy

The project should continue to be implemented incrementally.

Do NOT implement the entire auction engine at once.

Recommended sequence:

Foundation
    ↓
Players
    ↓
Tournament
    ↓
Teams
    ↓
Owners
    ↓
Team Logos
    ↓
Auction Models
    ↓
Auction Session
    ↓
Player Selection
    ↓
Bid Validation
    ↓
Bid Timer
    ↓
Last Call
    ↓
Sold/Purchase
    ↓
Pause/Resume/Stop
    ↓
Auction History
    ↓
Final Team/Roster Views
    ↓
Testing & Hardening


Each stage should be tested before moving to the next.

53. Current Development Position

Completed through:

Team Logo


The next major area is the auction database/model foundation.

Before writing auction code, the required auction behavior should be reviewed against this document and any new requirements should be added here.

54. Change Management

Whenever a major requirement changes, update this file.

For example:

Requirement:
Maximum players per team changed from 20 to 18.


Update the relevant tournament rule section.

Do not rely only on conversation history for important project decisions.

This file should remain the project's single high-level specification.

55. Golden Rule

When implementing future features:

Do not break existing working behavior
just to add a new feature.


Prefer:

New requirement
     ↓
Update specification
     ↓
Design database/state flow
     ↓
Implement
     ↓
Test
     ↓
Continue


The bot should remain modular and maintainable as the auction logic becomes more complex.


### One recommendation

Keep this file at the **project root**:

```text
Telegram_Auction_Bot/
├── PROJECT_SPEC.md   ← this file
├── README.md
├── app/
├── data/
├── migrations/
└── ...


This will be our reference going forward. When we make a new decision, we can update the relevant section rather than relying on the chat history.

Next after this: we can continue with the auction foundation, but before coding it I'd have us define the exact auction database entities and state transitions so the timer/pause/resume/last-call behavior doesn't become difficult to change later.