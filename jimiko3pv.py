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

        


@bot.tree.command(name="rename", description="เปลี่ยนชื่อห้องส่วนตัว")
async def rename(interaction: discord.Interaction, new_name: str):
    """คำสั่งสำหรับเปลี่ยนชื่อห้องเสียงส่วนตัว"""

    room = None

    # ตรวจสอบห้องที่ผู้ใช้สร้าง
    for r_name, r_data in private_rooms.items():
        if r_data['owner'] == interaction.user:
            room = r_data
            break

    if not room:
        await interaction.response.send_message("มึงไม่มีห้องส่วนตัวอีควาย !", ephemeral=True)
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
        private_rooms[new_name]['channel'] = channel  # ทำให้ข้อมูลใหม่ที่เก็บอยู่ใน private_rooms เป็นชื่อใหม่
        await interaction.response.send_message(f"ห้องของคุณเปลี่ยนชื่อเป็น '{new_name}' เรียบร้อยแล้ว ครับ/ค่ะ ", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("ไม่มีสิทธิ์ไอโง่", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"An error occurred while renaming the channel: {str(e)}", ephemeral=True)




@bot.tree.command(name="move", description="ย้ายคนเข้าห้องส่วนตัว")
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
        await interaction.response.send_message("ไม่มีสิทธิ์ไอโง่", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"An error occurred while moving the user: {str(e)}", ephemeral=True)



@bot.tree.command(name="permit", description="เพิ่มผู้ใช้เข้าห้อง")
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
        await interaction.response.send_message(f"คุณได้เพิ่มผู้ใช้ท่านนี้ {user.mention} เข้าห้องส่วนตัวแล้ว ครับ/ค่ะ", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("ไม่มีสิทธิ์ไอโง่", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"ERROR: {str(e)}", ephemeral=True)



async def check_and_delete_empty_channel(channel):
    while True:
        await asyncio.sleep(1)
        if len(channel.members) == 0:
            await channel.delete()
            print(f"Channel '{channel.name}' was deleted because it's empty.")
            break



server_on()

bot.run(os.getenv('TOKEN'))
