import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os  # ใช้ os สำหรับการโหลด TOKEN จากไฟล์แยก

from myserver import server_on

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# เก็บข้อมูลห้องที่สร้างขึ้น
private_rooms = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    # Sync the slash commands with Discord
    synced = await bot.tree.sync()
    print(f"{len(synced)} command(s)")

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name == "Create Private Room":
        guild = member.guild
        room_name = f"{member.name}"

        # ค้นหาหมวดหมู่ที่ต้องการ (หมวดหมู่ที่ชื่อว่า "Private Rooms")
        category = discord.utils.get(guild.categories, name="Private Rooms")

        # ถ้าไม่พบหมวดหมู่ ให้สร้างหมวดหมู่ใหม่
        if not category:
            category = await guild.create_category("Private Rooms")

        # ตั้งค่าการเข้าห้องให้ทุกคนไม่สามารถเข้าห้องได้ (except เจ้าของห้อง)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),  # ไม่ให้ทุกคนเข้าห้องและไม่เห็นห้อง
            member: discord.PermissionOverwrite(connect=True, view_channel=True)  # เจ้าของห้องสามารถเข้าห้องได้
        }

        new_channel = await guild.create_voice_channel(room_name, overwrites=overwrites, category=category)
        await member.move_to(new_channel)
        
        # เก็บข้อมูลห้องที่สร้างขึ้น
        private_rooms[room_name] = {'channel': new_channel, 'owner': member}
        await check_and_delete_empty_channel(new_channel)

@bot.tree.command(name="voice", description="Manage permissions for your private voice room")
async def voice(interaction: discord.Interaction, action: str, user_id: str):
    """คำสั่งสำหรับจัดการสิทธิ์การเข้าห้องเสียงส่วนตัว"""
    
    # ลบช่องว่างที่ไม่จำเป็นออกจาก user_id
    user_id = user_id.strip()

    # ตรวจสอบว่า user_id เป็นตัวเลขหรือไม่
    if not user_id.isdigit():
        await interaction.response.send_message("Please enter a valid user ID (a number).", ephemeral=True)
        return

    # แปลง user_id เป็นจำนวนเต็ม
    try:
        user_id = int(user_id)
    except ValueError:
        await interaction.response.send_message("User ID should be a valid number.", ephemeral=True)
        return

    room = None

    # ตรวจสอบห้องที่ผู้ใช้สร้าง
    for r_name, r_data in private_rooms.items():
        if r_data['owner'] == interaction.user:
            room = r_data
            break

    if not room:
        await interaction.response.send_message("You don't have a private room or you are not the owner!", ephemeral=True)
        return

    channel = room['channel']

    if action == "permit":
        try:
            # ค้นหาผู้ใช้จาก user_id
            user = await interaction.guild.fetch_member(user_id)
            if not user:
                await interaction.response.send_message(f"User with ID {user_id} not found.", ephemeral=True)
                return

            # ให้สิทธิ์ให้ผู้ใช้สามารถเข้าห้องได้
            await channel.set_permissions(user, connect=True, view_channel=True)
            await interaction.response.send_message(f"User {user.mention} has been permitted to join your private room.", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to modify this channel.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"An error occurred while setting permissions: {str(e)}", ephemeral=True)

    elif action == "deny":
        try:
            user = await interaction.guild.fetch_member(user_id)
            if not user:
                await interaction.response.send_message(f"User with ID {user_id} not found.", ephemeral=True)
                return

            # ปฏิเสธการเข้าห้อง
            await channel.set_permissions(user, connect=False, view_channel=False)
            await interaction.response.send_message(f"User {user.mention} has been denied from joining your private room.", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to modify this channel.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"An error occurred while setting permissions: {str(e)}", ephemeral=True)

    else:
        await interaction.response.send_message("Invalid action. Please use 'permit' or 'deny' as the action.", ephemeral=True)

async def check_and_delete_empty_channel(channel):
    while True:
        await asyncio.sleep(2)
        if len(channel.members) == 0:
            await channel.delete()
            print(f"Channel '{channel.name}' was deleted because it's empty.")
            break

server_on()

bot.run(os.getenv('TOKEN'))
