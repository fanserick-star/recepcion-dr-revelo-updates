export default {
  async fetch(request) {
    const url = new URL(request.url);
    const imageUrl = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/assets/whatsapp/recordatorios_de_citas_header.jpg";

    if (url.pathname === "/" || url.pathname === "/header.jpg") {
      const r = await fetch(imageUrl, {
        cf: { cacheTtl: 86400, cacheEverything: true }
      });

      if (!r.ok) {
        return new Response("No se pudo cargar la imagen", { status: 502 });
      }

      return new Response(r.body, {
        status: 200,
        headers: {
          "content-type": "image/jpeg",
          "cache-control": "public, max-age=86400"
        }
      });
    }

    return new Response("Not found", { status: 404 });
  }
};
