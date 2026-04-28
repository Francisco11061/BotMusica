import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
from collections import deque
import os
from dotenv import load_dotenv

# --- CONFIGURACIÓN ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
# ---------------------

# Cola global por servidor {guild_id: deque([track, ...])}
queues: dict[int, deque] = {}

def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


# ─────────────────────────────────────────
#  VISTA DE CONTROLES
# ─────────────────────────────────────────
class Controles(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player

    def _player_valido(self) -> bool:
        return self.player and self.player.connected

    @discord.ui.button(label="Pausar/Reanudar", emoji="⏯️", style=discord.ButtonStyle.blurple)
    async def pausar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player_valido():
            return await interaction.response.send_message("❌ El bot ya no está conectado.", ephemeral=True)
        if self.player.paused:
            await self.player.pause(False)
            await interaction.response.send_message("▶️ Música reanudada", ephemeral=True)
        else:
            await self.player.pause(True)
            await interaction.response.send_message("⏸️ Música pausada", ephemeral=True)

    @discord.ui.button(label="Saltar", emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def saltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player_valido():
            return await interaction.response.send_message("❌ El bot ya no está conectado.", ephemeral=True)
        await self.player.stop()
        await interaction.response.send_message("⏭️ Canción saltada", ephemeral=True)

    @discord.ui.button(label="Vol -10", emoji="🔉", style=discord.ButtonStyle.secondary)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player_valido():
            return await interaction.response.send_message("❌ El bot ya no está conectado.", ephemeral=True)
        nuevo = max(0, self.player.volume - 10)
        await self.player.set_volume(nuevo)
        await interaction.response.send_message(f"🔉 Volumen: **{nuevo}%**", ephemeral=True)

    @discord.ui.button(label="Vol +10", emoji="🔊", style=discord.ButtonStyle.secondary)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player_valido():
            return await interaction.response.send_message("❌ El bot ya no está conectado.", ephemeral=True)
        nuevo = min(200, self.player.volume + 10)
        await self.player.set_volume(nuevo)
        await interaction.response.send_message(f"🔊 Volumen: **{nuevo}%**", ephemeral=True)

    @discord.ui.button(label="Desconectar", emoji="🛑", style=discord.ButtonStyle.red)
    async def desconectar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player_valido():
            return await interaction.response.send_message("❌ El bot ya no está conectado.", ephemeral=True)
        gid = interaction.guild_id
        if gid in queues:
            queues[gid].clear()
        await self.player.disconnect()
        await interaction.response.send_message("👋 ¡Chao pescao!", ephemeral=True)
        self.stop()


# ─────────────────────────────────────────
#  BOT
# ─────────────────────────────────────────
class BotMusica(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        node = wavelink.Node(uri="https://lavalink.devamop.in", password="DevamOP")
        await wavelink.Pool.connect(nodes=[node], client=self)
        await self.tree.sync()
        print("Slash commands sincronizados.")

    async def on_ready(self):
        print(f"¡Bot conectado como {self.user}!")

    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: wavelink.Player = payload.player
        if player is None:
            return

        guild_id = player.guild.id
        queue = get_queue(guild_id)

        if queue:
            siguiente = queue.popleft()
            await player.play(siguiente)
            canal = getattr(player, "text_channel", None)
            if canal:
                controles = Controles(player=player)
                await canal.send(
                    f"🎶 Ahora suena: **{siguiente.title}** — {siguiente.author}",
                    view=controles
                )
        else:
            canal = getattr(player, "text_channel", None)
            if canal:
                await canal.send("✅ Cola vacía. ¡Añade más canciones con `/play`!")


bot = BotMusica()


# ─────────────────────────────────────────
#  SLASH COMMANDS
# ─────────────────────────────────────────

@bot.tree.command(name="play", description="Reproduce una canción de YouTube o SoundCloud")
@app_commands.describe(busqueda="Nombre o URL de la canción")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send("❌ ¡Entra a un canal de voz primero!")

    guild = interaction.guild
    voice_channel = interaction.user.voice.channel

    vc: wavelink.Player = guild.voice_client  # type: ignore
    if not vc:
        vc = await voice_channel.connect(cls=wavelink.Player, self_deaf=False)

    vc.text_channel = interaction.channel  # type: ignore

    tracks = await wavelink.Playable.search(busqueda, source="scsearch")
    if not tracks:
        return await interaction.followup.send("❌ No encontré nada con ese nombre.")

    track = tracks[0]
    queue = get_queue(guild.id)

    if vc.playing:
        queue.append(track)
        pos = len(queue)
        await interaction.followup.send(
            f"📋 Añadido a la cola (posición **#{pos}**): **{track.title}** — {track.author}"
        )
    else:
        await vc.play(track)
        controles = Controles(player=vc)
        await interaction.followup.send(
            f"🎶 Reproduciendo: **{track.title}** — {track.author}",
            view=controles
        )


@bot.tree.command(name="cola", description="Muestra las canciones en cola")
async def cola(interaction: discord.Interaction):
    queue = get_queue(interaction.guild_id)

    vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
    actual = f"🎵 **Sonando ahora:** {vc.current.title}\n\n" if vc and vc.current else ""

    if not queue:
        return await interaction.response.send_message(
            f"{actual}📋 La cola está vacía.", ephemeral=True
        )

    lineas = [f"`{i+1}.` {t.title} — {t.author}" for i, t in enumerate(queue)]
    embed = discord.Embed(
        title="🎶 Cola de reproducción",
        description=actual + "\n".join(lineas),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="saltar", description="Salta la canción actual")
async def saltar(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not vc or not vc.playing:
        return await interaction.response.send_message("❌ No hay nada reproduciéndose.", ephemeral=True)
    await vc.stop()
    await interaction.response.send_message("⏭️ Canción saltada.")


@bot.tree.command(name="volumen", description="Ajusta el volumen (0–200)")
@app_commands.describe(nivel="Nivel de volumen entre 0 y 200")
async def volumen(interaction: discord.Interaction, nivel: int):
    vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not vc:
        return await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)
    nivel = max(0, min(200, nivel))
    await vc.set_volume(nivel)
    emoji = "🔇" if nivel == 0 else "🔉" if nivel < 50 else "🔊"
    await interaction.response.send_message(f"{emoji} Volumen ajustado a **{nivel}%**")


@bot.tree.command(name="pausar", description="Pausa o reanuda la música")
async def pausar(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not vc:
        return await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)
    if vc.paused:
        await vc.pause(False)
        await interaction.response.send_message("▶️ Música reanudada.")
    else:
        await vc.pause(True)
        await interaction.response.send_message("⏸️ Música pausada.")


@bot.tree.command(name="limpiar", description="Limpia la cola de canciones")
async def limpiar(interaction: discord.Interaction):
    queue = get_queue(interaction.guild_id)
    queue.clear()
    await interaction.response.send_message("🗑️ Cola limpiada.")


@bot.tree.command(name="desconectar", description="Desconecta el bot del canal de voz")
async def desconectar(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not vc:
        return await interaction.response.send_message("❌ No estoy en ningún canal.", ephemeral=True)
    gid = interaction.guild_id
    if gid in queues:
        queues[gid].clear()
    await vc.disconnect()
    await interaction.response.send_message("👋 ¡Hasta luego!")


if __name__ == "__main__":
    bot.run(TOKEN)