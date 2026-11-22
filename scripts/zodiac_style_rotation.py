"""Seven original zodiac styles; rotate Monday to Sunday."""
import datetime as dt
STYLES=(
 ("STYLE_01","kawaii sticker","rounded sticker outlines, vivid pastel, friendly eyes"),
 ("STYLE_02","watercolor storybook","warm translucent watercolor on textured paper"),
 ("STYLE_03","3D plush clay","fluffy fabric and three-dimensional toy clay, soft studio light"),
 ("STYLE_04","Korean pastel webtoon","crisp Korean pastel webtoon, friendly expressive shapes"),
 ("STYLE_05","traditional Korean papercut","layered Korean hanji papercut, folk colors and ornament"),
 ("STYLE_06","gouache picturebook","rich cozy gouache brush texture, picturebook colors"),
 ("STYLE_07","glossy mascot","glossy premium original mascots, luminous soft reflections"),
)
def style_for_day(day):
    ident,name,prompt=STYLES[dt.date.fromisoformat(day).weekday()]
    return {"id":ident,"name":name,"prompt":prompt}
def week_ids(day):
    d=dt.date.fromisoformat(day);m=d-dt.timedelta(days=d.weekday())
    return tuple(style_for_day((m+dt.timedelta(days=i)).isoformat())["id"] for i in range(7))
