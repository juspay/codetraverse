public enum Status {
    PENDING("pending", 0),
    IN_PROGRESS("in_progress", 1),
    COMPLETED("completed", 2),
    FAILED("failed", -1);
    
    private final String label;
    private final int code;
    
    Status(String label, int code) {
        this.label = label;
        this.code = code;
    }
    
    public String getLabel() {
        return label;
    }
    
    public int getCode() {
        return code;
    }
    
    public static Status fromCode(int code) {
        for (Status s : values()) {
            if (s.code == code) {
                return s;
            }
        }
        return PENDING;
    }
}
