package agenttrace

import (
	"context"
	"fmt"
	"os"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"
)

var (
	tracerProvider *sdktrace.TracerProvider
	tracer         trace.Tracer
)

// InitOptions allows configuring the AgentTrace initialization.
type InitOptions struct {
	Endpoint    string
	ServiceName string
	SessionID   string
	Tags        map[string]string
}

// Option is a function that configures InitOptions.
type Option func(*InitOptions)

// WithEndpoint sets the OTLP trace HTTP endpoint (e.g., localhost:8000).
func WithEndpoint(endpoint string) Option {
	return func(o *InitOptions) {
		o.Endpoint = endpoint
	}
}

// WithServiceName sets the OpenTelemetry service name.
func WithServiceName(name string) Option {
	return func(o *InitOptions) {
		o.ServiceName = name
	}
}

// WithSessionID sets the session ID for grouping traces.
func WithSessionID(id string) Option {
	return func(o *InitOptions) {
		o.SessionID = id
	}
}

// WithTags sets arbitrary key-value tags on all traces.
func WithTags(tags map[string]string) Option {
	return func(o *InitOptions) {
		o.Tags = tags
	}
}

// Init sets up the global OpenTelemetry TracerProvider configured for AgentTrace.
// It respects standard OTel environment variables by default.
func Init(opts ...Option) error {
	options := &InitOptions{
		Endpoint:    os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
		ServiceName: os.Getenv("OTEL_SERVICE_NAME"),
	}

	if options.Endpoint == "" {
		options.Endpoint = "localhost:8002/v1/traces" // Default for local AgentTrace dashboard
	}
	if options.ServiceName == "" {
		options.ServiceName = "agenttrace-go-app"
	}

	for _, opt := range opts {
		opt(options)
	}

	expOpts := []otlptracehttp.Option{
		otlptracehttp.WithEndpointURL(options.Endpoint), // full URL, allowing proper parsing
		otlptracehttp.WithInsecure(), // Localhost development usually doesn't have TLS
	}

	exporter, err := otlptracehttp.New(context.Background(), expOpts...)
	if err != nil {
		return fmt.Errorf("failed to create otlp exporter: %w", err)
	}

	resAttrs := []attribute.KeyValue{
		semconv.ServiceName(options.ServiceName),
	}

	// Session ID from option or env var
	sessionID := options.SessionID
	if sessionID == "" {
		sessionID = os.Getenv("AGENTTRACE_SESSION_ID")
	}
	if sessionID != "" {
		resAttrs = append(resAttrs, attribute.String("agenttrace.session_id", sessionID))
	}

	// Tags from option or env var
	tags := options.Tags
	if tags == nil {
		tags = make(map[string]string)
	}
	envTags := os.Getenv("AGENTTRACE_TAGS")
	if envTags != "" {
		for _, pair := range splitAndTrim(envTags, ",") {
			parts := splitAndTrim(pair, "=")
			if len(parts) == 2 {
				if _, exists := tags[parts[0]]; !exists {
					tags[parts[0]] = parts[1]
				}
			}
		}
	}
	for k, v := range tags {
		resAttrs = append(resAttrs, attribute.String("agenttrace.tags."+k, v))
	}

	res, err := resource.New(context.Background(),
		resource.WithAttributes(resAttrs...),
	)
	if err != nil {
		return fmt.Errorf("failed to create resource: %w", err)
	}

	tracerProvider = sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)

	otel.SetTracerProvider(tracerProvider)
	tracer = tracerProvider.Tracer("agenttrace-go")

	return nil
}

// Shutdown gracefully flushes traces and shuts down the tracer provider.
// It is idempotent and respects the context timeout.
func Shutdown(ctx context.Context) error {
	if tracerProvider != nil {
		err := tracerProvider.Shutdown(ctx)
		tracerProvider = nil
		return err
	}
	return nil
}

// TrackAgent creates an agenttrace.agent span and passes a new context to the provided function.
// This ensures that child spans (like tool calls) correctly inherit the parent trace.
func TrackAgent(ctx context.Context, name string, f func(context.Context) error) error {
	if tracer == nil {
		tracer = otel.Tracer("agenttrace-go") // Fallback if init wasn't called directly
	}

	ctx, span := tracer.Start(ctx, name, trace.WithSpanKind(trace.SpanKindInternal))
	defer span.End()

	span.SetAttributes(attribute.String("agenttrace.type", "agent"))

	err := f(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
	}

	return err
}

// TrackTool creates an agenttrace.tool span and passes a new context to the provided function.
func TrackTool(ctx context.Context, name string, f func(context.Context) error) error {
	if tracer == nil {
		tracer = otel.Tracer("agenttrace-go")
	}

	ctx, span := tracer.Start(ctx, name, trace.WithSpanKind(trace.SpanKindInternal))
	defer span.End()

	span.SetAttributes(
		attribute.String("agenttrace.type", "tool"),
		attribute.String("agent.tool.name", name),
	)

	err := f(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
	}

	return err
}

// splitAndTrim splits s by sep and trims whitespace from each part.
func splitAndTrim(s, sep string) []string {
	result := make([]string, 0)
	for _, part := range strings.Split(s, sep) {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}
