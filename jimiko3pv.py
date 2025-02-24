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
    # ตรวจสอบว่า member ถูกย้ายเข้ามาห้อง
    if after.channel and after.channel.name == "Create Private Room":
        guild = member.guild
        room_name = f"{member.name}"

        # ค้นหาหมวดหมู่ "Private Rooms"
        category = discord.utils.get(guild.categories, name="Private Rooms")

        if not category:
            category = await guild.create_category("Private Rooms")

        # ตั้งค่าสิทธิ์สำหรับเจ้าของห้องและผู้ที่ย้ายเข้ามา
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
            member: discord.PermissionOverwrite(connect=True, view_channel=True, send_messages=True)  # เจ้าของห้องสามารถเข้าห้องได้และพิมพ์ข้อความได้
        }

        # สร้างห้อง
        new_channel = await guild.create_voice_channel(room_name, overwrites=overwrites, category=category)

        # ย้ายสมาชิกไปห้องเสียง
        await member.move_to(new_channel)

        # เก็บข้อมูลห้องที่สร้างขึ้น
        private_rooms[room_name] = {'channel': new_channel, 'owner': member}

        # ตรวจสอบห้องที่ว่างและลบห้องเมื่อไม่มีคนอยู่
        await check_and_delete_empty_channel(new_channel)

    # ตรวจสอบเมื่อสมาชิกออกจากห้อง (หรือเปลี่ยนห้อง)
    if before.channel and before.channel.name == "none" and not after.channel:
        room_name = f"{member.name}"
        if room_name in private_rooms:
            room = private_rooms[room_name]
            channel = room['channel']

            # ปรับสิทธิ์การเข้าห้องให้ไม่สามารถเข้าได้และไม่เห็นห้อง
            await channel.set_permissions(member, view_channel=False, connect=False)

            # แจ้งผู้ใช้ว่าไม่สามารถเข้าห้องได้
            #await member.send(f"You have left the private voice room '{room_name}', and you can no longer see or join the room unless permitted.")
            
            # ตรวจสอบห้องที่ว่างและลบห้องเมื่อไม่มีคนอยู่
            await check_and_delete_empty_channel(channel)

    # ตรวจสอบหากผู้ใช้เปลี่ยนห้องจากห้องที่ถูกย้ายเข้ามา (ต้องการออกห้อง)
    if before.channel and before.channel.name != "Create Private Room" and after.channel != before.channel:
        room_name = f"{member.name}"
        if room_name in private_rooms:
            room = private_rooms[room_name]
            channel = room['channel']

            # ปรับสิทธิ์การเข้าห้องให้ไม่สามารถเข้าได้และไม่เห็นห้อง
            await channel.set_permissions(member, view_channel=False, connect=False)

            # แจ้งผู้ใช้ว่าไม่สามารถเข้าห้องได้
            await member.send(f"You have left the private voice room '{room_name}', and you can no longer see or join the room unless permitted.")

        # ตรวจสอบห้องที่ว่างและลบห้องเมื่อไม่มีคนอยู่
        await check_and_delete_empty_channel(channel)

        


@bot.tree.command(name="rename", description="Change the name of your private voice room")
async def rename(interaction: discord.Interaction, new_name: str):
    """คำสั่งสำหรับเปลี่ยนชื่อห้องเสียงส่วนตัว"""

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

    # ตรวจสอบว่าชื่อใหม่ไม่ซ้ำกับห้องอื่น
    if discord.utils.get(channel.guild.voice_channels, name=new_name):
        await interaction.response.send_message(f"A channel with the name '{new_name}' already exists. Please choose a different name.", ephemeral=True)
        return

    try:
        # เปลี่ยนชื่อห้อง
        await channel.edit(name=new_name)
        # อัปเดตชื่อห้องใน private_rooms
        private_rooms[new_name] = private_rooms.pop(channel.name)
        private_rooms[new_name]['channel'] = channel
        await interaction.response.send_message(f"Your private room has been renamed to '{new_name}'.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to change the channel name.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"An error occurred while renaming the channel: {str(e)}", ephemeral=True)



@bot.tree.command(name="move", description="Move a user into your private voice room")
async def move(interaction: discord.Interaction, user_id: str):
    """คำสั่งสำหรับย้ายผู้ใช้ไปยังห้องส่วนตัว"""
    
    room = None

    # ตรวจสอบห้องที่ผู้ใช้สร้าง
    for r_name, r_data in private_rooms.items():
        if r_data['owner'] == interaction.user:
            room = r_data
            break

    if not room:
        await interaction.response.send_message("คุณไม่ใช่เจ้าของห้องไอควาย !", ephemeral=True)
        return

    voice_channel = room['channel']

    # ค้นหาผู้ใช้จาก user_id
    user = await interaction.guild.fetch_member(user_id)
    if not user:
        await interaction.response.send_message(f"User with ID {user_id} not found.", ephemeral=True)
        return

    try:
        # ย้ายผู้ใช้ไปห้องเสียง
        await user.move_to(voice_channel)

        # ให้ผู้ใช้สามารถพิมพ์ข้อความในช่องข้อความได้
        await voice_channel.set_permissions(user, send_messages=True, view_channel=False, connect=True)
        
        await interaction.response.send_message(f"คุณได้ย้ายคนนี้ {user.mention} เข้ามาในห้องของคุณแล้ว ครับ/ค่ะ .", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to move this user.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"An error occurred while moving the user: {str(e)}", ephemeral=True)



@bot.tree.command(name="permit", description="Permit a user to view and join your private voice room")
async def permit(interaction: discord.Interaction, user_id: str):
    """คำสั่งสำหรับอนุญาตให้ผู้ใช้เห็นและเข้าห้องส่วนตัว"""

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

    # ค้นหาผู้ใช้จาก user_id
    user = await interaction.guild.fetch_member(user_id)
    if not user:
        await interaction.response.send_message(f"User with ID {user_id} not found.", ephemeral=True)
        return

    try:
        # ให้ผู้ใช้สามารถเห็นห้อง (view_channel) และเข้าห้องได้ (connect)
        await channel.set_permissions(user, view_channel=True, connect=True)
        await interaction.response.send_message(f"User {user.mention} has been permitted to view and join your private room.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to modify this channel.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"An error occurred while setting permissions: {str(e)}", ephemeral=True)



async def check_and_delete_empty_channel(channel):
    while True:
        await asyncio.sleep(2)
        if len(channel.members) == 0:
            await channel.delete()
            print(f"Channel '{channel.name}' was deleted because it's empty.")
            break



server_on()

bot.run(os.getenv('TOKEN'))
