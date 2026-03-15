package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/CURSED-ME/AgentTrace/agenttrace-go"
	"github.com/CURSED-ME/AgentTrace/agenttrace-go/instrumentation/openai"
	sashabaranov "github.com/sashabaranov/go-openai"
)

func main() {
	// Initialize AgentTrace OpenTelemetry Pipeline
	err := agenttrace.Init(
		agenttrace.WithServiceName("go-openai-agent"),
	)
	if err != nil {
		log.Fatalf("Failed to initialize AgentTrace: %v", err)
	}
	defer agenttrace.Shutdown(context.Background()) // Flush traces

	// Create a customized HTTPClient using the AgentTrace RoundTripper interceptor
	httpClient := &http.Client{
		Transport: &openai.RoundTripper{
			Base: http.DefaultTransport,
		},
	}

	config := sashabaranov.DefaultConfig(os.Getenv("OPENAI_API_KEY"))
	config.HTTPClient = httpClient

	client := sashabaranov.NewClientWithConfig(config)

	fmt.Println("Running trace-wrapped Agent...")
	err = agenttrace.TrackAgent(context.Background(), "basic_chat_agent", func(ctx context.Context) error {
		
		fmt.Println("Sending native sashabaranov/go-openai request...")
		resp, err := client.CreateChatCompletion(ctx, sashabaranov.ChatCompletionRequest{
			Model: sashabaranov.GPT4oMini,
			Messages: []sashabaranov.ChatCompletionMessage{
				{
					Role:    sashabaranov.ChatMessageRoleUser,
					Content: "Write a short haiku about Go programming and tracing.",
				},
			},
		})

		if err != nil {
			return err
		}

		fmt.Println("Response Extracted:", resp.Choices[0].Message.Content)
		return nil
	})

	if err != nil {
		log.Fatalf("Agent error: %v", err)
	}
}
