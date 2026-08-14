// ローカルプロセスをクラスタ文脈で動かしたときに何が見えるかを可視化する検証用サービス。
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type report struct {
	Mode         string `json:"mode"`
	Hostname     string `json:"hostname"`
	PID          int    `json:"pid"`
	Greeting     string `json:"greeting_from_configmap"`
	TokenEnv     string `json:"token_from_secret_env"`
	TokenFile    string `json:"token_from_mounted_file"`
	KubeHost     string `json:"kubernetes_service_host"`
	UpstreamURL  string `json:"upstream_url"`
	UpstreamBody string `json:"upstream_body"`
	UpstreamErr  string `json:"upstream_error,omitempty"`
}

func main() {
	mode := env("MODE", "app")
	port := env("PORT", "8080")

	if mode == "upstream" {
		http.HandleFunc("/", upstream)
	} else {
		http.HandleFunc("/", app)
	}

	fmt.Printf("listening mode=%s port=%s pid=%d\n", mode, port, os.Getpid())
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func upstream(w http.ResponseWriter, _ *http.Request) {
	host, _ := os.Hostname()
	writeJSON(w, map[string]string{
		"service":  "upstream",
		"hostname": host,
		"message":  "クラスタ内 DNS で到達できたら成功",
	})
}

func app(w http.ResponseWriter, _ *http.Request) {
	host, _ := os.Hostname()
	url := env("UPSTREAM_URL", "http://upstream.agentlab.svc.cluster.local")

	r := report{
		Mode:        "app",
		Hostname:    host,
		PID:         os.Getpid(),
		Greeting:    env("GREETING", "(未設定)"),
		TokenEnv:    mask(env("API_TOKEN", "")),
		TokenFile:   mask(readFile("/etc/demo/token")),
		KubeHost:    env("KUBERNETES_SERVICE_HOST", "(未設定)"),
		UpstreamURL: url,
	}

	body, err := fetch(url)
	if err != nil {
		r.UpstreamErr = err.Error()
	} else {
		r.UpstreamBody = body
	}

	writeJSON(w, r)
}

func fetch(url string) (string, error) {
	c := &http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(b)), nil
}

func readFile(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// mask は値の有無と先頭だけを示す。検証ログに秘密そのものを残さない。
func mask(s string) string {
	if s == "" {
		return "(取得できず)"
	}
	if len(s) <= 4 {
		return "****"
	}
	return s[:4] + strings.Repeat("*", len(s)-4)
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}
