package main

import (
	"context"
	"fmt"
	"log"

	"github.com/CURSED-ME/AgentTrace/agenttrace-go"
)

func simulatedDatabaseTool(ctx context.Context, userID string) error {
	return agenttrace.TrackTool(ctx, "fetch_user_data", func(ctx context.Context) error {
		fmt.Printf("Fetching user data from DB for ID: %s...\\n", userID)
		// Simulating work...
		return nil
	})
}

func main() {
	err := agenttrace.Init(agenttrace.WithServiceName("tool-testing-agent"))
	if err != nil {
		log.Fatalf("Init failed: %v", err)
	}
	defer agenttrace.Shutdown(context.Background())

	err = agenttrace.TrackAgent(context.Background(), "workflow_agent", func(ctx context.Context) error {
		fmt.Println("Agent started.")
		return simulatedDatabaseTool(ctx, "U-819324")
	})

	if err != nil {
		log.Fatalf("Error: %v", err)
	}

	fmt.Println("AgentTrace recorded gracefully!")
}
