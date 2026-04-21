public interface IProcessor {
    void process(String data);
    
    String getResult();
    
    boolean isValid();
    
    default boolean validate(String input) {
        return input != null && !input.isEmpty();
    }
    
    static void reset() {
        System.out.println("Reset processor");
    }
}
