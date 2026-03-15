package openai

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"
)

// RoundTripper spans OpenAI requests and extracts GenAI semantic attributes.
type RoundTripper struct {
	Base http.RoundTripper
}

// ensure interfaces are satisfied
var _ http.RoundTripper = (*RoundTripper)(nil)

type chatRequest struct {
	Model    *string       `json:"model"`
	Messages []interface{} `json:"messages"`
}

type chatResponse struct {
	Model   *string `json:"model"`
	Choices []struct {
		Message struct {
			Content *string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
}

// RoundTrip executes a single HTTP transaction and creates a span.
func (rt *RoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	base := rt.Base
	if base == nil {
		base = http.DefaultTransport
	}

	tracer := otel.Tracer("agenttrace-go/openai")
	ctx, span := tracer.Start(req.Context(), "chat.completions.create", trace.WithSpanKind(trace.SpanKindClient))
	defer span.End()

	span.SetAttributes(
		semconv.ServerAddress(req.URL.Host),
		attribute.String("agenttrace.type", "llm_call"), // Custom UI classifier
		attribute.String("gen_ai.system", "openai"),
	)

	// Attempt to parse the request body
	if req.Body != nil {
		bodyBytes, err := io.ReadAll(req.Body)
		if err == nil {
			req.Body = io.NopCloser(bytes.NewBuffer(bodyBytes)) // restore body

			var chatReq chatRequest
			if err := json.Unmarshal(bodyBytes, &chatReq); err == nil {
				if chatReq.Model != nil {
					span.SetAttributes(attribute.String("gen_ai.request.model", *chatReq.Model))
				}
				if len(chatReq.Messages) > 0 {
					msgBytes, _ := json.Marshal(chatReq.Messages)
					span.SetAttributes(attribute.String("gen_ai.prompt", string(msgBytes)))
				}
			}
		}
	}

	req = req.WithContext(ctx)
	res, err := base.RoundTrip(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return res, err
	}

	// Read and parse response body
	if res.Body != nil {
		bodyBytes, err := io.ReadAll(res.Body)
		if err == nil {
			res.Body = io.NopCloser(bytes.NewBuffer(bodyBytes)) // restore body

			var chatRes chatResponse
			if err := json.Unmarshal(bodyBytes, &chatRes); err == nil {
				if chatRes.Model != nil {
					span.SetAttributes(attribute.String("gen_ai.response.model", *chatRes.Model))
				}
				if chatRes.Usage != nil {
					span.SetAttributes(
						attribute.Int("gen_ai.usage.input_tokens", chatRes.Usage.PromptTokens),
						attribute.Int("gen_ai.usage.output_tokens", chatRes.Usage.CompletionTokens),
					)
				}
				if len(chatRes.Choices) > 0 && chatRes.Choices[0].Message.Content != nil {
					span.SetAttributes(attribute.String("gen_ai.completion", *chatRes.Choices[0].Message.Content))
				}
			}
		}
	}

	return res, nil
}
