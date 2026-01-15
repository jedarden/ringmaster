//! Static file serving for embedded frontend

use axum::{
    body::Body,
    http::{header, Request, StatusCode, Uri},
    response::{IntoResponse, Response},
};
use rust_embed::RustEmbed;

#[derive(RustEmbed)]
#[folder = "target/frontend"]
struct Assets;

pub async fn static_handler(uri: Uri) -> impl IntoResponse {
    let path = uri.path().trim_start_matches('/');

    // If path is empty or doesn't have an extension, serve index.html
    let path = if path.is_empty() || !path.contains('.') {
        "index.html"
    } else {
        path
    };

    match Assets::get(path) {
        Some(content) => {
            let mime = mime_guess::from_path(path).first_or_octet_stream();
            Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, mime.as_ref())
                .body(Body::from(content.data.into_owned()))
                .unwrap()
        }
        None => {
            // SPA fallback: serve index.html for unmatched routes
            match Assets::get("index.html") {
                Some(content) => Response::builder()
                    .status(StatusCode::OK)
                    .header(header::CONTENT_TYPE, "text/html")
                    .body(Body::from(content.data.into_owned()))
                    .unwrap(),
                None => Response::builder()
                    .status(StatusCode::NOT_FOUND)
                    .body(Body::from("Not Found"))
                    .unwrap(),
            }
        }
    }
}

/// Middleware to serve static files, falling back to index.html for SPA routing
pub async fn serve_static_fallback(
    request: Request<Body>,
    next: axum::middleware::Next,
) -> Response {
    let path = request.uri().path();

    // If it's an API or WebSocket route, pass through
    if path.starts_with("/api") || path.starts_with("/health") {
        return next.run(request).await;
    }

    // Try to serve static file
    static_handler(request.uri().clone()).await.into_response()
}
