#!/usr/bin/env python3
"""
CopperHead Bot Template - Your custom Snake game AI.

This bot connects to a CopperHead server and plays Snake autonomously.
Modify the calculate_move() function to implement your own strategy!

QUICK START
-----------
1. Install dependencies:   pip install -r requirements.txt
2. Run:                     python mybot.py --server ws://localhost:8765/ws/

For Codespaces, use the wss:// URL shown in the terminal, e.g.:
    python mybot.py --server wss://your-codespace-url.app.github.dev/ws/

WHAT TO CHANGE
--------------
The calculate_move() function (around line 200) is where your bot decides
which direction to move. The default strategy is simple: chase the nearest
food while avoiding walls and snakes. You can make it smarter!

Ideas for improvement:
  - Avoid getting trapped in dead ends (flood fill)
  - Predict where the opponent will move
  - Use different strategies based on snake length
  - Block the opponent from reaching food
"""

import asyncio
import json
import argparse
import random
import websockets
from collections import deque


# ============================================================================
#  BOT CONFIGURATION - Change these to customize your bot
# ============================================================================

# The CopperHead server to connect to. Set this to your server's URL so you
# don't need to pass --server every time. Use "ws://" for local servers or
# "wss://" for Codespaces/remote servers.
GAME_SERVER = "ws://localhost:8765/ws/"

# Your bot's display name (shown to all players in the tournament)
BOT_NAME = "Gak1o AI"

# How your bot appears in logs
BOT_VERSION = "1.0"


# ============================================================================
#  BOT CLASS - Handles connection and game logic
# ============================================================================

class MyBot:
    """A CopperHead bot that connects to the server and plays Snake."""

    def __init__(self, server_url: str, name: str = None):
        self.server_url = server_url
        self.name = name or BOT_NAME
        self.player_id = None
        self.game_state = None
        self.running = False
        self.room_id = None
        # Grid dimensions (updated automatically from server)
        self.grid_width = 30
        self.grid_height = 20

    def log(self, msg: str):
        """Print a message to the console."""
        print(msg.encode("ascii", errors="replace").decode("ascii"))

    # ========================================================================
    #  CONNECTION - You probably don't need to change anything below here
    #  until you get to calculate_move()
    # ========================================================================

    async def wait_for_open_competition(self):
        """Wait until the server is reachable, then return.
        
        Bots always join the lobby regardless of competition state —
        the lobby is always available and the bot will wait there until
        the next competition starts.
        """
        import aiohttp

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        # Convert ws:// to http:// for the REST API
        http_url = base_url.replace("ws://", "http://").replace("wss://", "https://")

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{http_url}/status") as resp:
                        if resp.status == 200:
                            self.log("Server reachable - joining lobby...")
                            return True
                        else:
                            self.log(f"Server not ready (status {resp.status}), waiting...")
            except Exception as e:
                self.log(f"Cannot reach server: {e}, retrying...")

            await asyncio.sleep(5)

    async def connect(self):
        """Connect to the game server."""
        await self.wait_for_open_competition()

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        url = f"{base_url}/ws/join"

        try:
            self.log(f"Connecting to {url}...")
            self.ws = await websockets.connect(url)
            self.log("Connected! Joining lobby...")
            # Send join message to enter the lobby
            await self.ws.send(json.dumps({
                "action": "join",
                "name": self.name
            }))
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False

    async def play(self):
        """Main game loop. Runs until disconnected or eliminated."""
        if not await self.connect():
            self.log("Failed to connect. Exiting.")
            return

        self.running = True

        try:
            while self.running:
                message = await self.ws.recv()
                data = json.loads(message)
                await self.handle_message(data)
        except websockets.ConnectionClosed:
            self.log("Disconnected from server.")
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.running = False
            try:
                await self.ws.close()
            except Exception:
                pass
            self.log("Bot stopped.")

    async def handle_message(self, data: dict):
        """Process messages from the server and respond appropriately."""
        msg_type = data.get("type")

        if msg_type == "error":
            self.log(f"Server error: {data.get('message', 'Unknown error')}")
            self.running = False

        elif msg_type == "joined":
            # Server assigned us a player ID and room
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            self.log(f"Joined Arena {self.room_id} as Player {self.player_id}")

            # Tell the server we're ready to play
            await self.ws.send(json.dumps({
                "action": "ready",
                "mode": "two_player",
                "name": self.name
            }))
            self.log(f"Ready! Playing as '{self.name}'")

        elif msg_type == "state":
            # Game state update - this is where we decide our next move
            self.game_state = data.get("game")
            grid = self.game_state.get("grid", {})
            if grid:
                self.grid_width = grid.get("width", self.grid_width)
                self.grid_height = grid.get("height", self.grid_height)

            if self.game_state and self.game_state.get("running"):
                direction = self.calculate_move()
                if direction:
                    await self.ws.send(json.dumps({
                        "action": "move",
                        "direction": direction
                    }))

        elif msg_type == "start":
            self.log("Game started!")

        elif msg_type == "gameover":
            winner = data.get("winner")
            my_wins = data.get("wins", {}).get(str(self.player_id), 0)
            opp_id = 3 - self.player_id
            opp_wins = data.get("wins", {}).get(str(opp_id), 0)
            points_to_win = data.get("points_to_win", 5)

            if winner == self.player_id:
                self.log(f"Won! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")
            elif winner:
                self.log(f"Lost! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")
            else:
                self.log(f"Draw! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")

            # Signal ready for next game in the match
            await self.ws.send(json.dumps({
                "action": "ready",
                "name": self.name
            }))

        elif msg_type == "match_complete":
            winner_id = data.get("winner", {}).get("player_id")
            winner_name = data.get("winner", {}).get("name", "Unknown")
            final_score = data.get("final_score", {})
            my_score = final_score.get(str(self.player_id), 0)
            opp_id = 3 - self.player_id
            opp_score = final_score.get(str(opp_id), 0)

            if winner_id == self.player_id:
                self.log(f"Match won! Final: {my_score}-{opp_score}")
                self.log("Waiting for next round...")
            else:
                self.log(f"Match lost to {winner_name}. Final: {my_score}-{opp_score}")
                self.log("Eliminated. Exiting.")
                self.running = False

        elif msg_type == "match_assigned":
            # Assigned to a new match in the next tournament round
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            opponent = data.get("opponent", "Opponent")
            self.log(f"Next round! Arena {self.room_id} vs {opponent}")
            # Signal ready to the server
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif msg_type in ("lobby_joined", "lobby_update"):
            # In the lobby waiting for the competition to start
            if msg_type == "lobby_joined":
                self.log(f"Joined lobby as '{data.get('name', self.name)}'")

        elif msg_type in ("lobby_left", "lobby_kicked"):
            self.log("Removed from lobby.")
            self.running = False

        elif msg_type == "competition_complete":
            champion = data.get("champion", {}).get("name", "Unknown")
            self.log(f"Tournament complete! Champion: {champion}")
            self.running = False

        elif msg_type == "waiting":
            self.log("Waiting for opponent...")

    def count_reachable_cells(self, start_pos, dangerous_set):
        """Standard BFS to count reachable cells from start_pos."""
        queue = deque([start_pos])
        visited = {start_pos}
        count = 0

        while queue:
            x, y = queue.popleft()
            count += 1
            # Maximum reachable count for our board size context
            if count > 200:
                break

            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.grid_width and 0 <= ny < self.grid_height:
                    if (nx, ny) not in dangerous_set and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        return count

    # ========================================================================
    #  YOUR AI STRATEGY - Modify calculate_move() to change how your bot plays
    # ========================================================================

    def calculate_move(self) -> str | None:
        """Decide which direction to move.
        
        Strategic Enhancements:
            1. Prioritize Grapes (grapes) over Apples (apple).
            2. Ignore food that is about to expire (lifetime < distance).
            3. Adopt a defensive posture (tail-chasing) when comfortably ahead in length.
        """
        if not self.game_state:
            return None

        snakes = self.game_state.get("snakes", {})
        my_snake = snakes.get(str(self.player_id))

        if not my_snake or not my_snake.get("body"):
            return None

        head = my_snake["body"][0]
        current_dir = my_snake.get("direction", "right")
        my_body = my_snake["body"]
        my_length = len(my_body)
        
        # Get opponent info
        opp_id = 3 - self.player_id
        opp_snake = snakes.get(str(opp_id))
        opp_length = len(opp_snake.get("body", [])) if opp_snake else 0

        # Get food items and filter by reachability (lifetime vs distance)
        foods = self.game_state.get("foods", [])
        reachable_foods = []
        for food in foods:
            dist = abs(head[0] - food["x"]) + abs(head[1] - food["y"])
            lifetime = food.get("lifetime")
            if lifetime is not None and lifetime < dist + 2:
                continue
            reachable_foods.append(food)

        # Find the best target food (Grapes prioritized)
        nearest_food = None
        nearest_dist = float('inf')
        for food in reachable_foods:
            dist = abs(head[0] - food["x"]) + abs(head[1] - food["y"])
            # Grapes are much better (increases us, shrinks them)
            # Give them a virtual distance bonus for prioritization
            if food.get("type") == "grapes":
                dist -= 12
            
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_food = food

        # Build a set of all dangerous positions
        dangerous = set()
        for s_id, snake_data in snakes.items():
            body = snake_data.get("body", [])
            if not body:
                continue
            
            # General dangerous tiles: all segments except the tail
            for segment in body[:-1]:
                dangerous.add((segment[0], segment[1]))
            
            # Opponent-specific danger: their head's next moves
            if str(s_id) != str(self.player_id):
                opp_head = body[0]
                # If we are smaller or equal, avoid meeting their head head-on
                if opp_length >= my_length:
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        dangerous.add((opp_head[0] + dx, opp_head[1] + dy))

        # Direction vectors
        directions = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0)
        }
        opposites = {"up": "down", "down": "up", "left": "right", "right": "left"}

        def is_safe(x, y):
            if x < 0 or x >= self.grid_width or y < 0 or y >= self.grid_height:
                return False
            return (x, y) not in dangerous

        # Find all physically possible moves (no reversing)
        possible_moves = []
        for direction, (dx, dy) in directions.items():
            if direction == opposites.get(current_dir):
                continue
            new_x, new_y = head[0] + dx, head[1] + dy
            if is_safe(new_x, new_y):
                # Calculate reachable area for this move
                reachable = self.count_reachable_cells((new_x, new_y), dangerous)
                # Tail-chasing special case: self-tail is safe to move toward if space is low
                is_tail = (new_x, new_y) == (my_body[-1][0], my_body[-1][1])
                possible_moves.append({
                    "direction": direction,
                    "x": new_x, "y": new_y,
                    "reachable": reachable,
                    "is_tail": is_tail
                })

        if not possible_moves:
            # Desperation: try the tail even if it's "not safe" in the set
            my_tail = my_body[-1]
            for direction, (dx, dy) in directions.items():
                if direction == opposites.get(current_dir):
                    continue
                if (head[0] + dx, head[1] + dy) == (my_tail[0], my_tail[1]):
                    return direction
            return current_dir

        best_dir = None
        best_score = float('-inf')

        for move in possible_moves:
            score = 0
            new_x, new_y = move["x"], move["y"]
            reachable = move["reachable"]

            # --- Survival is priority: huge bonus for reachable space ---
            if reachable < my_length:
                score -= 1000
            score += reachable * 10

            # --- Target food if it's safe to do so ---
            is_on_food = False
            for food in reachable_foods:
                if new_x == food["x"] and new_y == food["y"]:
                    # Is it safe to eat? (Don't eat if it traps us, but BFS handles this)
                    if food.get("type") == "grapes":
                        score += 800  # Grapes are delicious
                    else:
                        score += 400
                    is_on_food = True
                    break

            if nearest_food and not is_on_food:
                food_dist = abs(new_x - nearest_food["x"]) + abs(new_y - nearest_food["y"])
                # Only value food if we have enough space
                if reachable > my_length:
                    # Scale food value based on type in nearest_food as well
                    multiplier = 8 if nearest_food.get("type") == "grapes" else 4
                    score += (self.grid_width + self.grid_height - food_dist) * multiplier

            # --- Strategic Defensiveness ---
            # If we are comfortably longer than the opponent, prioritize survival over food
            is_ahead = (my_length > opp_length + 2)
            
            # Tail chasing bonus
            if move["is_tail"] or reachable < my_length * 1.5:
                dist_to_tail = abs(new_x - my_body[-1][0]) + abs(new_y - my_body[-1][1])
                safety_weight = 4 if is_ahead else 2
                score += (self.grid_width + self.grid_height - dist_to_tail) * safety_weight

            # --- Edge avoidance ---
            edge_dist = min(new_x, self.grid_width - 1 - new_x,
                           new_y, self.grid_height - 1 - new_y)
            # Stay centered more if we are ahead (wait out the opponent)
            edge_weight = 4 if is_ahead else 2
            score += edge_dist * edge_weight

            if score > best_score:
                best_score = score
                best_dir = move["direction"]

        return best_dir


# ============================================================================
#  MAIN - Parse command line arguments and start the bot
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CopperHead Bot")
    parser.add_argument("--server", "-s", default=GAME_SERVER,
                        help=f"Server WebSocket URL (default: {GAME_SERVER})")
    parser.add_argument("--name", "-n", default=None,
                        help=f"Bot display name (default: {BOT_NAME})")
    parser.add_argument("--difficulty", "-d", type=int, default=5,
                        help="AI difficulty level 1-10 (accepted for compatibility, not yet used)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress console output")
    args = parser.parse_args()

    bot = MyBot(args.server, name=args.name)

    print(f"{bot.name} v{BOT_VERSION}")
    print(f"  Server: {args.server}")
    print()

    await bot.play()


if __name__ == "__main__":
    asyncio.run(main())
