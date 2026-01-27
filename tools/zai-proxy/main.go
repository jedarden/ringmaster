package main

import (
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

func main() {
	apiKey := os.Getenv("ZAI_API_KEY")
	if apiKey == "" {
		log.Fatal("ZAI_API_KEY environment variable required")
	}

	target := "https://api.z.ai"

	client := &http.Client{
		Timeout: 5 * time.Minute,
		// Don't follow redirects automatically
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Build upstream URL
		upstreamURL := target + r.URL.Path
		if r.URL.RawQuery != "" {
			upstreamURL += "?" + r.URL.RawQuery
		}

		// Create upstream request
		upstreamReq, err := http.NewRequestWithContext(r.Context(), r.Method, upstreamURL, r.Body)
		if err != nil {
			log.Printf("Error creating request: %v", err)
			http.Error(w, "Bad request", http.StatusBadRequest)
			return
		}

		// Copy headers from original request
		for key, values := range r.Header {
			for _, value := range values {
				upstreamReq.Header.Add(key, value)
			}
		}

		// Override with correct host and auth
		upstreamReq.Header.Set("Host", "api.z.ai")
		upstreamReq.Header.Set("Authorization", "Bearer "+apiKey)

		// Make the request
		resp, err := client.Do(upstreamReq)
		if err != nil {
			log.Printf("Error forwarding request: %v", err)
			http.Error(w, "Upstream error", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		// Copy response headers
		for key, values := range resp.Header {
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}

		// Set status code
		w.WriteHeader(resp.StatusCode)

		// Stream the response body
		// Use small buffer for streaming SSE responses
		buf := make([]byte, 1024)
		flusher, canFlush := w.(http.Flusher)

		for {
			n, err := resp.Body.Read(buf)
			if n > 0 {
				_, writeErr := w.Write(buf[:n])
				if writeErr != nil {
					log.Printf("Error writing response: %v", writeErr)
					return
				}
				if canFlush {
					flusher.Flush()
				}
			}
			if err == io.EOF {
				break
			}
			if err != nil {
				log.Printf("Error reading response: %v", err)
				return
			}
		}
	})

	log.Println("Z.AI proxy listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
