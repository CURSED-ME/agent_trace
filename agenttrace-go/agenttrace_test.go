package agenttrace

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

func setupTestExporter() (*tracetest.SpanRecorder, *sdktrace.TracerProvider) {
	exp := tracetest.NewSpanRecorder()
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithSpanProcessor(exp),
	)
	otel.SetTracerProvider(tp)
	tracerProvider = tp
	tracer = tp.Tracer("test-tracer")
	return exp, tp
}

func TestTrackAgent_Success(t *testing.T) {
	exp, tp := setupTestExporter()
	defer tp.Shutdown(context.Background())

	err := TrackAgent(context.Background(), "test_agent", func(ctx context.Context) error {
		return nil
	})

	require.NoError(t, err)

	spans := exp.Ended()
	require.Len(t, spans, 1)

	span := spans[0]
	assert.Equal(t, "test_agent", span.Name())

	var typeAttr attribute.KeyValue
	for _, attr := range span.Attributes() {
		if attr.Key == "agenttrace.type" {
			typeAttr = attr
		}
	}
	assert.Equal(t, "agent", typeAttr.Value.AsString())
}

func TestTrackTool_ErrorHandling(t *testing.T) {
	exp, tp := setupTestExporter()
	defer tp.Shutdown(context.Background())

	expectedErr := errors.New("tool execution failed")

	err := TrackTool(context.Background(), "test_tool", func(ctx context.Context) error {
		return expectedErr
	})

	require.ErrorIs(t, err, expectedErr)

	spans := exp.Ended()
	require.Len(t, spans, 1)

	span := spans[0]
	assert.Equal(t, "test_tool", span.Name())
	assert.Equal(t, codes.Error, span.Status().Code)
	assert.Equal(t, "tool execution failed", span.Status().Description)

	var typeAttr, nameAttr attribute.KeyValue
	for _, attr := range span.Attributes() {
		if attr.Key == "agenttrace.type" {
			typeAttr = attr
		}
		if attr.Key == "agent.tool.name" {
			nameAttr = attr
		}
	}
	assert.Equal(t, "tool", typeAttr.Value.AsString())
	assert.Equal(t, "test_tool", nameAttr.Value.AsString())
}
